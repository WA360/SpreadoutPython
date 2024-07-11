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

                    chapter = Chapter.objects.create(
                        name=title,
                        start_page=start_page,
                        end_page=end_page,
                        level=level,
                        bookmarked=False,  # 기본값을 False로 설정
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

            # 챕터 계층 구조에 따른 연결 생성
            def create_connections(chapters):
                for i, chapter in enumerate(chapters):
                    for j in range(i + 1, len(chapters)):
                        next_chapter = chapters[j]
                        if next_chapter.level > chapter.level:
                            PageConnection.objects.create(
                                pdf_file=pdf_file,
                                source=chapter,
                                target=next_chapter,
                                similarity=1.0  # similarity 값을 1.0으로 고정
                            )
                        else:
                            break

            create_connections(chapters)
            logger.info("Chapter-based page connections created")

            # ID를 반환하는 응답
            return Response({"message": "PDF and connections have been saved.", "pdf_file_id": pdf_file.id}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error occurred: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
# 챗봇 파이프라인
class ChatBotPipelineView(APIView):
    def post(self, request):
        try:
            # s3_url과 question 확인
            if 's3_url' not in request.data or 'question' not in request.data:
                logger.error("s3_url or question not found in request")
                return Response({"error": "s3_url and question must be provided."}, status=status.HTTP_400_BAD_REQUEST)
            
            s3_url = request.data['s3_url']
            question = request.data['question']
            
            # S3 버킷 및 파일 이름 추출
            bucket_name, file_name = self.parse_s3_url(s3_url)
            
            # S3에서 파일 읽기
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
            
            file_obj = s3_client.get_object(Bucket=bucket_name, Key=file_name)
            file_content = file_obj['Body'].read()
            file_io = BytesIO(file_content)
            file_io.seek(0)
            
            # PDF 파일에서 텍스트 추출 및 인덱싱
            pdf_document = fitz.open(stream=file_io, filetype="pdf")
            pages_text = [pdf_document.load_page(page_num).get_text() for page_num in range(len(pdf_document))]
            logger.info(f"Extracted text from {len(pdf_document)} pages")
            
            # Sentence-BERT 모델 로드
            model = SentenceTransformer('all-mpnet-base-v2')
            logger.info("SentenceTransformer model loaded")
            
            # 페이지 텍스트를 임베딩으로 변환하여 인덱싱
            page_embeddings = [model.encode(page_text).tolist() for page_text in pages_text]
            logger.info("Page embeddings created")
            
            # 질문 임베딩 생성
            question_embedding = model.encode(question).tolist()
            
            # 유사도 계산
            similarities = [util.pytorch_cos_sim(question_embedding, page_embedding) for page_embedding in page_embeddings]
            most_similar_page = np.argmax(similarities)
            most_similar_text = pages_text[most_similar_page]
            logger.info(f"Most similar page: {most_similar_page}")
            
            # LLM 파이프라인을 사용하여 답변 생성
            response_text = self.llm_pipeline(most_similar_text, question)
            
            final_response = {
                "answer": response_text,
                "page": most_similar_page + 1  # 페이지는 1부터 시작하도록 조정
            }
            
            return Response(final_response, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error occurred: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def parse_s3_url(self, s3_url):
        # S3 URL에서 버킷 이름과 파일 이름을 추출
        s3_components = s3_url.replace("https://", "").split(".s3.")
        bucket_name = s3_components[0]
        file_name = s3_components[1].split("amazonaws.com/")[1]
        return bucket_name, file_name
    
    def llm_pipeline(self, text, question):
        # 대규모 LLM 모델 예시
        llm_model = pipeline("text-generation", model="llama-8B")  # 예시 모델
        # llama 8B 모델 로드
        llama_model = pipeline("text-generation", model="llama-8B")  # 예시 모델
        
        # 질문과 텍스트를 결합하여 모델에 입력
        input_text = f"Question: {question}\nContext: {text}\nAnswer:"
        
        # 대규모 LLM 모델로 텍스트 처리
        processed_text = llm_model(input_text, max_length=1024, num_return_sequences=1)[0]['generated_text']
        
        # llama 8B 모델로 응답을 인간 친화적으로 개선
        refined_response = llama_model(processed_text, max_length=1024, num_return_sequences=1)[0]['generated_text']
        
        return refined_response