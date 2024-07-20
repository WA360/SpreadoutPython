import pymupdf as fitz  # PyMuPDF
import logging
import boto3
from io import BytesIO
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
import numpy as np
from .models import PDFFile, PageConnection, Chapter
from django.conf import settings
from django.contrib.auth.models import User  # 장고에서 기본으로 제공하는 user db model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser
import logging

logger = logging.getLogger(__name__)

# pdf를 받아 s3에 저장, 챕터정보 추출하여 db에 저장, 챕터정보를 바탕으로 연결 정보 생성하여 db에 저장
class RecommendView(APIView):
    def post(self, request):
        try:
            # 파일 및 유저 ID 정보 확인
            if 'file' not in request.FILES or 'user_id' not in request.data:
                logger.error("File or user_id not found in request")
                return Response({"error": "File and user ID must be provided."}, status=status.HTTP_400_BAD_REQUEST)

            file = request.FILES['file']
            user_id = request.data['user_id']

            # 유저 확인
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                logger.error(f"User with ID {user_id} does not exist.")
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            file_name = file.name
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )

            # S3에 파일 업로드
            try:
                s3_client.upload_fileobj(file, settings.AWS_STORAGE_BUCKET_NAME, file_name)
                file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
                logger.info(f"File {file_name} uploaded to S3 at {file_url}")
            except Exception as e:
                logger.error(f"Failed to upload file to S3: {e}")
                return Response({"error": "Failed to upload file to S3."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # PDFFile 객체 생성
            pdf_file = PDFFile.objects.create(filename=file_name, user=user, url=file_url)
            logger.info(f"PDFFile object created with id {pdf_file.id}")

            # PDF 파일에서 페이지 텍스트를 추출하여 총 페이지 수 확인
            file_obj = s3_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_name)
            file_content = file_obj['Body'].read()
            file_io = BytesIO(file_content)
            file_io.seek(0)

            pdf_document = fitz.open(stream=file_io, filetype="pdf")
            pages_text = [pdf_document.load_page(page_num).get_text() for page_num in range(len(pdf_document))]
            logger.info(f"Extracted text from {len(pages_text)} pages")

            # 챕터 추출 함수 정의
            def save_chapters_from_toc(toc, pdf_file, total_pages):
                chapters = []
                current_group = 1  # 현재 그룹 번호
                for i in range(len(toc)):
                    level, title, start_page = toc[i]
                    end_page = None

                    # 다음 챕터의 시작 페이지를 찾고 현재 챕터의 end_page로 설정
                    if i + 1 < len(toc):
                        next_level, next_title, next_start_page = toc[i + 1]
                        if next_level <= level:
                            end_page = next_start_page - 1
                        else:
                            # 마지막 챕터의 경우, 마지막 페이지를 end_page로 설정
                            end_page = total_pages - 1
                    # `end_page`가 None일 경우 total_pages - 1로 설정
                    if end_page is None:
                        end_page = total_pages - 1

                    # 시작 페이지와 끝 페이지가 동일한 경우를 처리
                    if start_page > end_page:
                        end_page = start_page

                    # 그루핑
                    if level == 1:
                        # level 1 챕터의 경우 새로운 그룹 시작
                        current_group += 1

                    chapter = Chapter.objects.create(
                        name=title,
                        start_page=start_page,
                        end_page=end_page,
                        level=level,
                        group=current_group,  # 현재 그룹 번호로 설정
                        bookmarked=False,
                        pdf_file=pdf_file
                    )
                    chapters.append(chapter)
                return chapters

            toc = pdf_document.get_toc()
            if toc:
                chapters = save_chapters_from_toc(toc, pdf_file, len(pages_text))
                logger.info("Chapters information saved from TOC")
            else:
                logger.warning("No TOC found in PDF")
                chapters = []

        #     # 챕터 계층 구조에 따른 연결 생성
        #     def create_connections(chapters):
        #         for i, chapter in enumerate(chapters):
        #             for j in range(i + 1, len(chapters)):
        #                 next_chapter = chapters[j]
        #                 if next_chapter.level == chapter.level + 1:
        #                     PageConnection.objects.create(
        #                         pdf_file=chapter.pdf_file,
        #                         source=chapter,
        #                         target=next_chapter,
        #                         similarity=1.0  # 사용하지 않는 값
        #                     )
        #                 elif next_chapter.level <= chapter.level:
        #                     break

        #     create_connections(chapters)
        #     logger.info("Chapter-based page connections created")

        #     # ID를 반환하는 응답
        #     return Response({"message": "PDF and connections have been saved.", "pdf_file_id": pdf_file.id}, status=status.HTTP_200_OK)

        # except Exception as e:
        #     logger.error(f"Error occurred: {e}")
        #     return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # sentenceTranceformer 모델 로드
            model = SentenceTransformer('all-MiniLM-L6-v2')

            # 챕터 임베딩 생성
            chapter_texts = [chapter.name for chapter in chapters]
            chapter_embeddings = model.encode(chapter_texts)

            # 유사도 계산 및 연결 생성
            def create_connections_from_embeddings(chapters, embeddings):
                cosine_similarities = util.pytorch_cos_sim(embeddings, embeddings).numpy()
                for i, chapter in enumerate(chapters):
                    for j in range(i + 1, len(chapters)):
                        similarity = cosine_similarities[i][j]
                        if similarity > 0.75:  # 유사도 임계값 설정
                            PageConnection.objects.create(
                                pdf_file=chapter.pdf_file,
                                source=chapter,
                                target=chapters[j],
                                similarity=similarity
                            )

            create_connections_from_embeddings(chapters, chapter_embeddings)
            logger.info("Chapter-based page connections created using embeddings")
            # ID를 반환하는 응답
            return Response({"message": "PDF and connections have been saved.", "pdf_file_id": pdf_file.id}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error occurred: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
# 키워드 검색
class SearchView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            # 파일 및 검색어 정보 확인
            if 'file' not in request.FILES or 'keyword' not in request.data:
                return Response({"error": "File and keyword must be provided."}, status=status.HTTP_400_BAD_REQUEST)

            file = request.FILES['file']
            keyword = request.data['keyword']

            # PDF 텍스트 추출
            doc = fitz.open(stream=file.read(), filetype='pdf')

            # PDF 파일과 연결된 챕터를 찾기 위해 DB에서 필터링
            # 'pdf_file'을 정의하거나 필터링에 사용할 모델 필드가 필요합니다.
            # 예를 들어, 특정 PDF 파일에 연결된 챕터를 찾으려면 pdf_file_id 등을 사용해야 합니다.
            # 지금은 파일 업로드가 아닌 pdf_file 객체를 필요로 하므로 주석 처리
            # chapters = Chapter.objects.filter(pdf_file=pdf_file)  # pdf_file은 현재 정의되지 않음

            # 현재 검색에서는 PDF 파일에 연결된 챕터 정보가 필요 없으므로 아래와 같이
            chapters = Chapter.objects.all()  # 또는 특정 조건으로 필터링

            results = {}
            for chapter in chapters:
                page_start = chapter.start_page - 1
                page_end = chapter.end_page
                chapter_text = "".join([doc.load_page(i).get_text() for i in range(page_start, page_end)])
                if keyword.lower() in chapter_text.lower():
                    found_pages = set()
                    for i in range(page_start, page_end):
                        if keyword.lower() in doc.load_page(i).get_text().lower():
                            found_pages.add(i + 1)

                    # 챕터의 level이 가장 낮은 것을 저장하도록 수정
                    if chapter.level not in results or chapter.level < results[chapter.level]['level']:
                        results[chapter.level] = {
                            'id': chapter.id,
                            'name': chapter.name,
                            'start_page': chapter.start_page,
                            'found_pages': frozenset(found_pages),
                            'level': chapter.level
                        }

            # 결과를 level 오름차순으로 정렬하여 반환
            sorted_results = sorted(results.values(), key=lambda x: x['level'])

            return Response({'results': [{'id': res['id'], 'name': res['name'], 'page': res['start_page'], 'found_pages': res['found_pages']} for res in sorted_results]})

        except Exception as e:
            logger.error(f"Error occurred in SearchView: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)