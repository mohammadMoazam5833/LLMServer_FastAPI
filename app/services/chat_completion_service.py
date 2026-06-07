# from __future__ import annotations
#
# import json
# import logging
# import time
# import uuid
# from typing import AsyncIterator
#
# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from app.models.llm import LLMModel, Conversation
# from app.models.user import User
# from app.runtime.provider_manager import ProviderManager
# from app.services.chat_service import ChatService
# from app.services.openwebui_tasks import is_openwebui_internal_request
# from app.services.rag_service import retrieve_context
# from app.services.token_utils import estimate_message_tokens, estimate_text_tokens
# from app.schemas.schemas import ChatCompletionRequest
#
# logger = logging.getLogger(__name__)
#
# #
# # async def _flatten_content_async(message) -> str:
# #     """تبدیل ساختار پیام به متن ساده و اجرای غیربلاک‌کننده فرآیند چت مالتی‌مدیا"""
# #     raw = message.content if hasattr(message, "content") else message.get("content", "")
# #     images = message.images if hasattr(message, "images") else message.get("images", [])
# #
# #     if images:
# #         from app.services.rag_service import ocr_base64_image
# #         texts = []
# #         if isinstance(raw, str) and raw:
# #             texts.append(raw)
# #         for img_url in images:
# #             if img_url.startswith("data:image"):
# #                 # فراخوانی نسخه نوین و اسینک شده OCR
# #                 ocr_text = await ocr_base64_image(img_url)
# #                 if ocr_text:
# #                     texts.append(f"[OCR: {ocr_text}]")
# #         return "\n".join(texts)
# #
# #     if isinstance(raw, str):
# #         return raw
# #     if isinstance(raw, list):
# #         from app.services.rag_service import ocr_base64_image
# #         texts = []
# #         for part in raw:
# #             if not isinstance(part, dict):
# #                 continue
# #             if part.get("type") == "text":
# #                 texts.append(part.get("text", ""))
# #             elif part.get("type") == "image_url":
# #                 url = part.get("image_url", {}).get("url", "")
# #                 if url.startswith("data:image"):
# #                     ocr_text = await ocr_base64_image(url)
# #                     if ocr_text:
# #                         texts.append(f"[OCR: {ocr_text}]")
# #         return "\n".join(texts)
# #     return str(raw)
# #
# async def _flatten_content_async(message) -> tuple[str, str]:
#     """
#     خروجی اول: متن نهایی ادغام شده همراه با OCR (برای مدل)
#     خروجی دوم: فقط متن خالص تایپ شده توسط کاربر (برای کوئری سرچ RAG)
#     """
#     from app.services.rag_service import ocr_base64_image
#
#     raw = message.content if hasattr(message, "content") else message.get("content", "")
#     images = message.images if hasattr(message, "images") else message.get("images", [])
#
#     all_parts_text = []
#     pure_user_text = []  # ذخیره اختصاصی سوال کاربر
#
#     # ۱. پردازش بدنه چندبخشی فرانت‌بند
#     if isinstance(raw, list):
#         for part in raw:
#             if not isinstance(part, dict):
#                 if isinstance(part, str):
#                     all_parts_text.append(part)
#                     pure_user_text.append(part)
#                 continue
#
#             # اگر پارت متنی بود، هم برای مدل می‌رود هم برای کوئری RAG
#             if part.get("type") == "text" or "text" in part:
#                 file_text = part.get("text", "")
#                 if file_text:
#                     all_parts_text.append(file_text)
#                     pure_user_text.append(file_text)
#
#             elif part.get("type") == "image_url":
#                 url_data = part.get("image_url", {})
#                 url = url_data.get("url", "") if isinstance(url_data, dict) else str(url_data)
#                 if url.startswith("data:image"):
#                     ocr_text = await ocr_base64_image(url)
#                     if ocr_text:
#                         all_parts_text.append(f"[OCR Context: {ocr_text}]")
#
#     elif isinstance(raw, str) and raw:
#         all_parts_text.append(raw)
#         pure_user_text.append(raw)
#
#     # ۲. پردازش آرایه تصاویر مجزا
#     if isinstance(images, list) and images:
#         for img in images:
#             url = img if isinstance(img, str) else (img.get("url") or img.get("image_url", {}).get("url", ""))
#             if url and url.startswith("data:image"):
#                 ocr_text = await ocr_base64_image(url)
#                 if ocr_text:
#                     all_parts_text.append(f"[OCR Context: {ocr_text}]")
#
#     final_flat = "\n\n".join([t for t in all_parts_text if t.strip()])
#     final_query = " ".join([t for t in pure_user_text if t.strip()])
#
#     return final_flat, final_query
# # async def _get_last_user_async(messages) -> str | None:
# #     for m in reversed(messages):
# #         role = m.role if hasattr(m, "role") else m["role"]
# #         if role == "user":
# #             return await _flatten_content_async(m)
# #     return None
# #
#
# async def _get_last_user_async(messages) -> str | None:
#     """ادغام تمام بخش‌های متنی و فایلی ارسال شده توسط کاربر در درخواست فعلی"""
#     user_contents = []
#
#     for m in messages:
#         role = m.role if hasattr(m, "role") else m["role"]
#         if role == "user":
#             flat_content = await _flatten_content_async(m)
#             if flat_content:
#                 user_contents.append(flat_content)
#
#     return "\n\n".join(user_contents) if user_contents else None
# async def _get_system_async(messages) -> str:
#     for m in messages:
#         role = m.role if hasattr(m, "role") else m["role"]
#         if role == "system":
#             return await _flatten_content_async(m)
#     return ""
#
#
# async def _to_openai_messages_async(messages) -> list[dict]:
#     return [
#         {
#             "role": m.role if hasattr(m, "role") else m["role"],
#             "content": await _flatten_content_async(m),
#         }
#         for m in messages
#     ]
#
#
# def _with_rag_context(messages: list[dict], context: str) -> list[dict]:
#     if not context:
#         return messages
#
#     system_message = {
#         "role": "system",
#         "content": (
#             "You are given retrieved document context from uploaded files. "
#             "Use this context only when it directly supports the user query. "
#             "If the context is not relevant, do not force it into the answer. "
#             "Answer from your knowledge when the retrieved context does not apply.\n\n"
#             f"{context}"
#         ),
#     }
#     if messages and messages[0]["role"] == "system":
#         merged = messages.copy()
#         merged[0] = {
#             "role": "system",
#             "content": f"{messages[0]['content']}\n\n{system_message['content']}",
#         }
#         return merged
#     return [system_message, *messages]
#
#
# def _estimate_tokens(text: str) -> int:
#     return estimate_text_tokens(text)
#
#
# def _message_token_count(message: dict) -> int:
#     return estimate_message_tokens(message)
#
#
# def _trim_messages_to_budget(messages: list[dict], max_prompt_tokens: int) -> list[dict]:
#     if not messages:
#         return messages
#
#     system_messages = [message for message in messages if message["role"] == "system"]
#     chat_messages = [message for message in messages if message["role"] != "system"]
#
#     system_tokens = sum(_message_token_count(message) for message in system_messages)
#     chat_budget = max(256, max_prompt_tokens - system_tokens)
#
#     kept_reversed: list[dict] = []
#     used = 0
#     for message in reversed(chat_messages):
#         message_tokens = _message_token_count(message)
#         if kept_reversed and used + message_tokens > chat_budget:
#             break
#         kept_reversed.append(message)
#         used += message_tokens
#
#     kept_chat = list(reversed(kept_reversed))
#     dropped = len(chat_messages) - len(kept_chat)
#     if dropped:
#         logger.info(
#             "Trimmed %d OpenAI-compatible history messages to fit prompt budget",
#             dropped,
#         )
#
#     return [*system_messages, *kept_chat]
#
#
# def _resolve_max_tokens(data_max_tokens: int, model_max_output: int | None) -> int:
#     cap = model_max_output or 4096
#     requested = int(data_max_tokens)
#     resolved = min(requested, cap)
#     logger.info("🔢 max_tokens: request=%d | model_cap=%d | resolved=%d", requested, cap, resolved)
#     return resolved
#
#
# def _prepare_provider_messages(
#     messages_payload: list[dict],
#     model: LLMModel,
#     data_max_tokens: int,
#     rag_context: str,
# ) -> list[dict]:
#     messages = _with_rag_context(messages_payload, rag_context)
#     max_output_tokens = _resolve_max_tokens(data_max_tokens, model.max_output_tokens)
#     context_length = model.context_length or 8192
#     safety_margin = 64
#     prompt_budget = max(512, context_length - max_output_tokens - safety_margin)
#
#     messages = _trim_messages_to_budget(messages, prompt_budget)
#     prompt_tokens = sum(_message_token_count(message) for message in messages)
#     max_output_tokens = min(max_output_tokens, max(1, context_length - prompt_tokens - safety_margin))
#
#     rag_len = len(rag_context) if rag_context else 0
#     logger.info(
#         "📝 prepare_provider_messages | model_ctx=%d | max_output=%d | prompt_budget=%d | prompt_tokens=%d | rag_context_chars=%d | total_msgs=%d",
#         context_length, max_output_tokens, prompt_budget, prompt_tokens, rag_len, len(messages)
#     )
#
#     return messages
#
#
# def _file_ids(data: ChatCompletionRequest) -> list[uuid.UUID]:
#     if not data.files:
#         return []
#     ids: list[uuid.UUID] = []
#     for file in data.files:
#         try:
#             ids.append(uuid.UUID(str(file.id)))
#         except (ValueError, AttributeError):
#             continue
#     return ids
#
#
# async def _load_model(data: ChatCompletionRequest, db: AsyncSession) -> LLMModel:
#     result = await db.execute(
#         select(LLMModel).where(LLMModel.id == data.model, LLMModel.is_active == True)
#     )
#     model = result.scalar_one_or_none()
#     if model is None:
#         from fastapi import HTTPException, status
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model '{data.model}' not found")
#     return model
#
#
# async def _create_internal_task_completion(
#     data: ChatCompletionRequest,
#     db: AsyncSession,
# ) -> dict:
#     model = await _load_model(data, db)
#     generator = ProviderManager.get_provider(model)
#     max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
#     openai_msgs = await _to_openai_messages_async(data.messages)
#     messages = _trim_messages_to_budget(
#         openai_msgs,
#         max(512, (model.context_length or 8192) - max_tokens - 512),
#     )
#     response = await generator.generate(
#         messages,
#         max_tokens=max_tokens,
#         temperature=float(data.temperature),
#     )
#     content = response.get("text", "")
#     return {
#         "id": f"chatcmpl-{uuid.uuid4()}",
#         "object": "chat.completion",
#         "created": int(time.time()),
#         "model": model.id,
#         "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
#         "conversation_id": str(data.conversation_id) if data.conversation_id else None,
#         "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
#     }
#
#
# async def _create_internal_task_completion_stream(
#     data: ChatCompletionRequest,
#     db: AsyncSession,
# ) -> AsyncIterator[str]:
#     model = await _load_model(data, db)
#     generator = ProviderManager.get_provider(model)
#     max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
#     cmpl_id = f"chatcmpl-{uuid.uuid4()}"
#     created = int(time.time())
#
#     openai_msgs = await _to_openai_messages_async(data.messages)
#     trimmed_msgs = _trim_messages_to_budget(
#         openai_msgs,
#         max(512, (model.context_length or 8192) - max_tokens - 512),
#     )
#
#     async for token in generator.generate_stream(
#         trimmed_msgs,
#         max_tokens=max_tokens,
#         temperature=float(data.temperature),
#     ):
#         chunk = {
#             "id": cmpl_id,
#             "object": "chat.completion.chunk",
#             "created": created,
#             "model": model.id,
#             "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
#         }
#         yield f"data: {json.dumps(chunk)}\n\n"
#
#     yield "data: [DONE]\n\n"
#
#
# async def _prepare(
#     data: ChatCompletionRequest,
#     user: User,
#     db: AsyncSession,
# ) -> tuple[ChatService, Conversation, str, str]:
#     model = await _load_model(data, db)
#     conv_id = data.conversation_id
#
#     system_prompt = await _get_system_async(data.messages) or "You are a helpful coding assistant."
#     last_user_msg = await _get_last_user_async(data.messages) or ""
#
#     # گیت ایمنی: اجرای RAG تنها در صورتی که شناسه فایل وجود داشته باشد
#     file_ids = _file_ids(data)
#     rag_context = ""
#     if file_ids:
#         rag_context = await retrieve_context(db, user.id, file_ids, last_user_msg)
#
#     if rag_context:
#         system_prompt = (
#             f"{system_prompt}\n\n"
#             "Use the following retrieved document context when it is relevant. "
#             "If the context does not answer the user, say so and answer from general knowledge.\n\n"
#             f"{rag_context}"
#         )
#
#     if conv_id:
#         result = await db.execute(
#             select(Conversation).where(
#                 Conversation.id == conv_id,
#                 Conversation.user_id == user.id,
#             )
#         )
#         conv = result.scalar_one_or_none()
#         if conv is None:
#             conv = Conversation(
#                 id=conv_id,
#                 user_id=user.id,
#                 model_id=model.id,
#                 system_prompt=system_prompt,
#             )
#             db.add(conv)
#             await db.flush()
#     else:
#         conv = Conversation(
#             user_id=user.id,
#             model_id=model.id,
#             system_prompt=system_prompt,
#         )
#         db.add(conv)
#         await db.flush()
#
#     generator = ProviderManager.get_provider(model)
#     service = ChatService(
#         generator=generator,
#         model_id=model.id,
#         conversation=conv,
#         user_id=user.id,
#         db=db,
#         system_prompt=system_prompt,
#         model_path=model.model_path,
#         context_length=model.context_length,
#         max_output_tokens=model.max_output_tokens,
#     )
#     return service, conv, model.id, last_user_msg
#
#
# # async def create_openai_chat_completion(
# #     data: ChatCompletionRequest,
# #     user: User,
# #     db: AsyncSession,
# # ) -> dict:
# #     if is_openwebui_internal_request(data.messages):
# #         return await _create_internal_task_completion(data, db)
# #
# #     logger.info(
# #         "🎯 create_openai_chat_completion | model_id=%s | request_max_tokens=%d | stream=%s",
# #         data.model, data.max_tokens, data.stream
# #     )
# #
# #     model = await _load_model(data, db)
# #     generator = ProviderManager.get_provider(model)
# #
# #     last_user_msg = await _get_last_user_async(data.messages) or ""
# #     file_ids = _file_ids(data)
# #     rag_context = ""
# #     if file_ids:
# #         rag_context = await retrieve_context(db, user.id, file_ids, last_user_msg)
# #
# #     openai_msgs = await _to_openai_messages_async(data.messages)
# #     messages = _prepare_provider_messages(openai_msgs, model, data.max_tokens, rag_context)
# #     max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
# #
# #     response = await generator.generate(
# #         messages,
# #         max_tokens=max_tokens,
# #         temperature=float(data.temperature),
# #     )
# #     content = response.get("text", "")
# #     logger.info("📥 response content length: %d chars", len(content))
# #     return {
# #         "id": f"chatcmpl-{uuid.uuid4()}",
# #         "object": "chat.completion",
# #         "created": int(time.time()),
# #         "model": model.id,
# #         "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
# #         "conversation_id": str(data.conversation_id) if data.conversation_id else None,
# #         "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
# #     }
# #
#
# async def create_openai_chat_completion(
#         data: ChatCompletionRequest,
#         user: User,
#         db: AsyncSession,
# ) -> dict:
#     if is_openwebui_internal_request(data.messages):
#         return await _create_internal_task_completion(data, db)
#
#     logger.info(
#         "🎯 create_openai_chat_completion | model_id=%s | request_max_tokens=%d",
#         data.model, data.max_tokens
#     )
#
#     model = await _load_model(data, db)
#     generator = ProviderManager.get_provider(model)
#
#     # داخل متد create_openai_chat_completion و نسخه stream آن:
#
#     openai_msgs = []
#     rag_search_query = ""  # 🌟 کوئری تمیز بدون آلودگی به متن سنگین OCR
#
#     for m in data.messages:
#         role = m.role if hasattr(m, "role") else m["role"]
#
#         # خروجی توپل را دریافت می‌کنیم
#         flat_content, pure_query = await _flatten_content_async(m)
#
#         openai_msgs.append({
#             "role": role,
#             "content": flat_content
#         })
#
#         if role == "user" and pure_query.strip():
#             rag_search_query = pure_query  # آخرین سوال متنی کاربر تثبیت می‌شود
#
#     # 🌟 حالا RAG را با کوئری فوق‌العاده تمیز و دقیق صدا می‌زنیم
#     file_ids = _file_ids(data)
#     rag_context = ""
#     if file_ids and rag_search_query:
#         logger.info("🔍 Running RAG with clean query: '%s'", rag_search_query[:100])
#         rag_context = await retrieve_context(db, user.id, file_ids, rag_search_query)
#     # آماده‌سازی و بررسی پرامپت‌ها بر اساس بودجه توکن مدل
#     messages = _prepare_provider_messages(openai_msgs, model, data.max_tokens, rag_context)
#     max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
#
#     response = await generator.generate(
#         messages,
#         max_tokens=max_tokens,
#         temperature=float(data.temperature),
#     )
#
#     content = response.get("text", "")
#     logger.info("📥 response content length: %d chars", len(content))
#     return {
#         "id": f"chatcmpl-{uuid.uuid4()}",
#         "object": "chat.completion",
#         "created": int(time.time()),
#         "model": model.id,
#         "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
#         "conversation_id": str(data.conversation_id) if data.conversation_id else None,
#         "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
#     }
# #
# # async def create_openai_chat_completion_stream(
# #     data: ChatCompletionRequest,
# #     user: User,
# #     db: AsyncSession,
# # ) -> AsyncIterator[str]:
# #     if is_openwebui_internal_request(data.messages):
# #         async for chunk in _create_internal_task_completion_stream(data, db):
# #             yield chunk
# #         return
# #
# #     logger.info(
# #         "📡 create_openai_chat_completion_stream | model_id=%s | request_max_tokens=%d",
# #         data.model, data.max_tokens
# #     )
# #
# #     model = await _load_model(data, db)
# #     generator = ProviderManager.get_provider(model)
# #
# #     last_user_msg = await _get_last_user_async(data.messages) or ""
# #     file_ids = _file_ids(data)
# #     rag_context = ""
# #     if file_ids:
# #         rag_context = await retrieve_context(db, user.id, file_ids, last_user_msg)
# #
# #     openai_msgs = await _to_openai_messages_async(data.messages)
# #     messages = _prepare_provider_messages(openai_msgs, model, data.max_tokens, rag_context)
# #     max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
# #
# #     cmpl_id = f"chatcmpl-{uuid.uuid4()}"
# #     created = int(time.time())
# #
# #     async for token in generator.generate_stream(
# #         messages,
# #         max_tokens=max_tokens,
# #         temperature=float(data.temperature),
# #     ):
# #         chunk = {
# #             "id": cmpl_id,
# #             "object": "chat.completion.chunk",
# #             "created": created,
# #             "model": model.id,
# #             "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
# #         }
# #         yield f"data: {json.dumps(chunk)}\n\n"
# #
# #     yield "data: [DONE]\n\n"
# async def create_openai_chat_completion_stream(
#         data: ChatCompletionRequest,
#         user: User,
#         db: AsyncSession,
# ) -> AsyncIterator[str]:
#     if is_openwebui_internal_request(data.messages):
#         async for chunk in _create_internal_task_completion_stream(data, db):
#             yield chunk
#         return
#
#     logger.info(
#         "📡 create_openai_chat_completion_stream | model_id=%s | request_max_tokens=%d",
#         data.model, data.max_tokens
#     )
#
#     model = await _load_model(data, db)
#     generator = ProviderManager.get_provider(model)
#
#     # 🌟 فلت کردن پیام‌ها به صورت یکپارچه و یک‌باره
#     openai_msgs = []
#     last_user_msg = ""
#
#     for m in data.messages:
#         role = m.role if hasattr(m, "role") else m["role"]
#         flat_content = await _flatten_content_async(m)
#
#         openai_msgs.append({
#             "role": role,
#             "content": flat_content
#         })
#
#         if role == "user" and flat_content:
#             last_user_msg = flat_content
#
#     file_ids = _file_ids(data)
#     rag_context = ""
#     if file_ids and last_user_msg:
#         rag_context = await retrieve_context(db, user.id, file_ids, last_user_msg)
#
#     messages = _prepare_provider_messages(openai_msgs, model, data.max_tokens, rag_context)
#     max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
#
#     cmpl_id = f"chatcmpl-{uuid.uuid4()}"
#     created = int(time.time())
#
#     async for token in generator.generate_stream(
#             messages,
#             max_tokens=max_tokens,
#             temperature=float(data.temperature),
#     ):
#         chunk = {
#             "id": cmpl_id,
#             "object": "chat.completion.chunk",
#             "created": created,
#             "model": model.id,
#             "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
#         }
#         yield f"data: {json.dumps(chunk)}\n\n"
#
#     yield "data: [DONE]\n\n"
#
#
# # ── Non-streaming ──────────────────────────────────────────────────────────────
#
# async def create_chat_completion(
#     data: ChatCompletionRequest,
#     user: User,
#     db: AsyncSession,
# ) -> dict:
#     if is_openwebui_internal_request(data.messages):
#         return await _create_internal_task_completion(data, db)
#
#     service, conv, model_id, msg = await _prepare(data, user, db)
#     max_output_cap = service._kwargs.get("max_output_tokens") or 4096
#     max_tokens = _resolve_max_tokens(data.max_tokens, max_output_cap)
#     res = await service.chat(msg, max_tokens)
#     return {
#         "id": f"chatcmpl-{uuid.uuid4()}",
#         "object": "chat.completion",
#         "created": int(time.time()),
#         "model": model_id,
#         "choices": [{"index": 0, "message": {"role": "assistant", "content": res["text"]}}],
#         "conversation_id": str(conv.id),
#         "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
#     }
#
#
# # ── Streaming ──────────────────────────────────────────────────────────────────
#
# async def create_chat_completion_stream(
#     data: ChatCompletionRequest,
#     user: User,
#     db: AsyncSession,
# ) -> AsyncIterator[str]:
#     if is_openwebui_internal_request(data.messages):
#         async for chunk in _create_internal_task_completion_stream(data, db):
#             yield chunk
#         return
#
#     service, conv, model_id, msg = await _prepare(data, user, db)
#     max_output_cap = service._kwargs.get("max_output_tokens") or 4096
#     max_tokens = _resolve_max_tokens(data.max_tokens, max_output_cap)
#     cmpl_id = f"chatcmpl-{uuid.uuid4()}"
#     created = int(time.time())
#
#     async for token in service.stream(msg, max_tokens):
#         chunk = {
#             "id": cmpl_id,
#             "object": "chat.completion.chunk",
#             "created": created,
#             "model": model_id,
#             "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
#         }
#         yield f"data: {json.dumps(chunk)}\n\n"
#
#     yield "data: [DONE]\n\n"


from __future__ import annotations

import json
import logging
import time
import uuid
from typing import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import LLMModel, Conversation
from app.models.user import User
from app.runtime.provider_manager import ProviderManager
from app.services.chat_service import ChatService
from app.services.openwebui_tasks import is_openwebui_internal_request
from app.services.rag_service import retrieve_context
from app.services.token_utils import estimate_message_tokens, estimate_text_tokens
from app.schemas.schemas import ChatCompletionRequest

logger = logging.getLogger(__name__)


# ─── HELPERS & EXTRACTION MULTIMEDIA ──────────────────────────────────────────

async def _flatten_content_async(message, include_ocr: bool = True) -> str:
    """
    تبدیل پایدار پیام‌های مالتی‌مدیا به متن ساده.
    فلگ include_ocr اجازه می‌دهد متن استخراج شده از عکس را برای کوئری‌های RAG حذف کنیم.
    """
    from app.services.rag_service import ocr_base64_image

    raw = message.content if hasattr(message, "content") else message.get("content", "")
    images = message.images if hasattr(message, "images") else message.get("images", [])
    texts = []

    # ۱. پردازش تصاویر مجزای آرایه تصاویر
    if include_ocr and isinstance(images, list) and images:
        for img_url in images:
            if isinstance(img_url, str) and img_url.startswith("data:image"):
                logger.info("📸 [Multi-File] Processing image via OCR...")
                ocr_text = await ocr_base64_image(img_url)
                if ocr_text:
                    texts.append(f"[OCR Context: {ocr_text}]")

    # ۲. پردازش بدنه چندبخشی (Multipart Payload)
    if isinstance(raw, list):
        for part in raw:
            if not isinstance(part, dict):
                if isinstance(part, str):
                    texts.append(part)
                continue

            part_type = part.get("type")
            if part_type == "text":
                file_text = part.get("text", "")
                if file_text:
                    texts.append(file_text)

            elif part_type == "image_url" and include_ocr:
                url_data = part.get("image_url", {})
                url = url_data.get("url", "") if isinstance(url_data, dict) else str(url_data)
                if url.startswith("data:image"):
                    logger.info("📸 [Multi-File] Processing embedded multipart image...")
                    ocr_text = await ocr_base64_image(url)
                    if ocr_text:
                        texts.append(f"[OCR Context: {ocr_text}]")

    elif isinstance(raw, str) and raw:
        texts.append(raw)
    elif raw:
        texts.append(str(raw))

    return "\n\n".join([t for t in texts if t.strip()])


async def _get_last_user_async(messages, include_ocr: bool = True) -> str | None:
    """ادغام بخش‌های متنی کاربر با امکان فیلترینگ دیتای سنگین OCR"""
    user_contents = []
    for m in messages:
        role = m.role if hasattr(m, "role") else m["role"]
        if role == "user":
            flat_content = await _flatten_content_async(m, include_ocr=include_ocr)
            if flat_content:
                user_contents.append(flat_content)
    return "\n\n".join(user_contents) if user_contents else None


async def _get_system_async(messages) -> str:
    for m in messages:
        role = m.role if hasattr(m, "role") else m["role"]
        if role == "system":
            return await _flatten_content_async(m, include_ocr=True)
    return ""


async def _to_openai_messages_async(messages) -> list[dict]:
    return [
        {
            "role": m.role if hasattr(m, "role") else m["role"],
            "content": await _flatten_content_async(m, include_ocr=True),
        }
        for m in messages
    ]


# ─── TOKEN BUDGET & CONTEXT MANAGEMENT ────────────────────────────────────────

def _with_rag_context(messages: list[dict], context: str) -> list[dict]:
    if not context:
        return messages

    system_message = {
        "role": "system",
        "content": (
            "You are given retrieved document context from uploaded files. "
            "Use this context only when it directly supports the user query. "
            "If the context is not relevant, do not force it into the answer. "
            "Answer from your knowledge when the retrieved context does not apply.\n\n"
            f"{context}"
        ),
    }
    if messages and messages[0]["role"] == "system":
        merged = messages.copy()
        merged[0] = {
            "role": "system",
            "content": f"{messages[0]['content']}\n\n{system_message['content']}",
        }
        return merged
    return [system_message, *messages]


def _trim_messages_to_budget(messages: list[dict], max_prompt_tokens: int) -> list[dict]:
    if not messages:
        return messages

    system_messages = [m for m in messages if m["role"] == "system"]
    chat_messages = [m for m in messages if m["role"] != "system"]

    system_tokens = sum(estimate_message_tokens(m) for m in system_messages)
    chat_budget = max(256, max_prompt_tokens - system_tokens)

    kept_reversed: list[dict] = []
    used = 0
    for message in reversed(chat_messages):
        message_tokens = estimate_message_tokens(message)
        if kept_reversed and used + message_tokens > chat_budget:
            break
        kept_reversed.append(message)
        used += message_tokens

    kept_chat = list(reversed(kept_reversed))
    dropped = len(chat_messages) - len(kept_chat)
    if dropped:
        logger.info("Trimmed %d OpenAI history messages to fit budget", dropped)

    return [*system_messages, *kept_chat]


def _resolve_max_tokens(data_max_tokens: int, model_max_output: int | None) -> int:
    cap = model_max_output or 4096
    resolved = min(int(data_max_tokens), cap)
    logger.info("🔢 max_tokens: request=%d | cap=%d | resolved=%d", int(data_max_tokens), cap, resolved)
    return resolved


def _prepare_provider_messages(
        messages_payload: list[dict],
        model: LLMModel,
        data_max_tokens: int,
        rag_context: str,
) -> list[dict]:
    messages = _with_rag_context(messages_payload, rag_context)
    max_output_tokens = _resolve_max_tokens(data_max_tokens, model.max_output_tokens)
    context_length = model.context_length or 8192
    safety_margin = 64
    prompt_budget = max(512, context_length - max_output_tokens - safety_margin)

    messages = _trim_messages_to_budget(messages, prompt_budget)
    prompt_tokens = sum(estimate_message_tokens(m) for m in messages)
    max_output_tokens = min(max_output_tokens, max(1, context_length - prompt_tokens - safety_margin))

    logger.info(
        "📝 Messages Prepared | ctx=%d | output=%d | prompt_tokens=%d | rag_chars=%d | total_msgs=%d",
        context_length, max_output_tokens, prompt_tokens, len(rag_context) if rag_context else 0, len(messages)
    )
    return messages


def _file_ids(data: ChatCompletionRequest) -> list[uuid.UUID]:
    if not data.files:
        return []
    ids: list[uuid.UUID] = []
    for file in data.files:
        try:
            ids.append(uuid.UUID(str(file.id)))
        except (ValueError, AttributeError):
            continue
    return ids


async def _load_model(data: ChatCompletionRequest, db: AsyncSession) -> LLMModel:
    result = await db.execute(select(LLMModel).where(LLMModel.id == data.model, LLMModel.is_active == True))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model '{data.model}' not found")
    return model


# ─── INTERNAL TASK HANDLING (OPEN-WEBUI INTERNALS) ───────────────────────────

async def _create_internal_task_completion(data: ChatCompletionRequest, db: AsyncSession) -> dict:
    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
    openai_msgs = await _to_openai_messages_async(data.messages)
    messages = _trim_messages_to_budget(openai_msgs, max(512, (model.context_length or 8192) - max_tokens - 512))

    response = await generator.generate(messages, max_tokens=max_tokens, temperature=float(data.temperature))
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model.id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": response.get("text", "")}}],
        "conversation_id": str(data.conversation_id) if data.conversation_id else None,
        "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
    }


async def _create_internal_task_completion_stream(data: ChatCompletionRequest, db: AsyncSession) -> AsyncIterator[str]:
    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
    cmpl_id, created = f"chatcmpl-{uuid.uuid4()}", int(time.time())

    openai_msgs = await _to_openai_messages_async(data.messages)
    trimmed_msgs = _trim_messages_to_budget(openai_msgs, max(512, (model.context_length or 8192) - max_tokens - 512))

    async for token in generator.generate_stream(trimmed_msgs, max_tokens=max_tokens,
                                                 temperature=float(data.temperature)):
        chunk = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model.id,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ─── MAIN CORE API ENDPOINTS ──────────────────────────────────────────────────

async def _prepare(data: ChatCompletionRequest, user: User, db: AsyncSession) -> tuple[
    ChatService, Conversation, str, str]:
    model = await _load_model(data, db)
    conv_id = data.conversation_id

    system_prompt = await _get_system_async(data.messages) or "You are a helpful coding assistant."
    last_user_msg = await _get_last_user_async(data.messages, include_ocr=True) or ""

    # استخراج کوئری پاکیزه متنی مجزا بدون نویزهای حجیم کدهای تصویر (OCR)
    rag_query = await _get_last_user_async(data.messages, include_ocr=False) or ""
    file_ids = _file_ids(data)
    rag_context = ""

    if file_ids and rag_query.strip():
        rag_context = await retrieve_context(db, user.id, file_ids, rag_query)

    if rag_context:
        system_prompt = (
            f"{system_prompt}\n\n"
            "Use the following retrieved document context when it is relevant. "
            "If the context does not answer the user, say so and answer from general knowledge.\n\n"
            f"{rag_context}"
        )

    if conv_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user.id))
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = Conversation(id=conv_id, user_id=user.id, model_id=model.id, system_prompt=system_prompt)
            db.add(conv)
            await db.flush()
    else:
        conv = Conversation(user_id=user.id, model_id=model.id, system_prompt=system_prompt)
        db.add(conv)
        await db.flush()

    generator = ProviderManager.get_provider(model)
    service = ChatService(
        generator=generator, model_id=model.id, conversation=conv, user_id=user.id, db=db,
        system_prompt=system_prompt, model_path=model.model_path, context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
    )
    return service, conv, model.id, last_user_msg


async def create_openai_chat_completion(data: ChatCompletionRequest, user: User, db: AsyncSession) -> dict:
    if is_openwebui_internal_request(data.messages):
        return await _create_internal_task_completion(data, db)

    logger.info("🎯 create_openai_chat_completion | model=%s | stream=%s", data.model, data.stream)
    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)

    # بهینه‌سازی کوئری سرچ دیتابیس
    rag_query = await _get_last_user_async(data.messages, include_ocr=False) or ""
    file_ids = _file_ids(data)
    rag_context = ""
    if file_ids and rag_query.strip():
        rag_context = await retrieve_context(db, user.id, file_ids, rag_query)

    openai_msgs = await _to_openai_messages_async(data.messages)
    messages = _prepare_provider_messages(openai_msgs, model, data.max_tokens, rag_context)
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)

    response = await generator.generate(messages, max_tokens=max_tokens, temperature=float(data.temperature))
    content = response.get("text", "")
    logger.info("📥 response content length: %d chars", len(content))
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model.id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "conversation_id": str(data.conversation_id) if data.conversation_id else None,
        "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
    }


async def create_openai_chat_completion_stream(data: ChatCompletionRequest, user: User, db: AsyncSession) -> \
AsyncIterator[str]:
    if is_openwebui_internal_request(data.messages):
        async for chunk in _create_internal_task_completion_stream(data, db):
            yield chunk
        return

    logger.info("📡 create_openai_chat_completion_stream | model=%s", data.model)
    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)

    # بهینه‌سازی کوئری سرچ دیتابیس
    rag_query = await _get_last_user_async(data.messages, include_ocr=False) or ""
    file_ids = _file_ids(data)
    rag_context = ""
    if file_ids and rag_query.strip():
        rag_context = await retrieve_context(db, user.id, file_ids, rag_query)

    openai_msgs = await _to_openai_messages_async(data.messages)
    messages = _prepare_provider_messages(openai_msgs, model, data.max_tokens, rag_context)
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)

    cmpl_id, created = f"chatcmpl-{uuid.uuid4()}", int(time.time())
    async for token in generator.generate_stream(messages, max_tokens=max_tokens, temperature=float(data.temperature)):
        chunk = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model.id,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ─── LEGACY SERVICE-BASED ENDPOINTS ───────────────────────────────────────────

async def create_chat_completion(data: ChatCompletionRequest, user: User, db: AsyncSession) -> dict:
    if is_openwebui_internal_request(data.messages):
        return await _create_internal_task_completion(data, db)

    service, conv, model_id, msg = await _prepare(data, user, db)
    max_tokens = _resolve_max_tokens(data.max_tokens, service._kwargs.get("max_output_tokens") or 4096)
    res = await service.chat(msg, max_tokens)
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": res["text"]}}],
        "conversation_id": str(conv.id),
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def create_chat_completion_stream(data: ChatCompletionRequest, user: User, db: AsyncSession) -> AsyncIterator[
    str]:
    if is_openwebui_internal_request(data.messages):
        async for chunk in _create_internal_task_completion_stream(data, db):
            yield chunk
        return

    service, conv, model_id, msg = await _prepare(data, user, db)
    max_tokens = _resolve_max_tokens(data.max_tokens, service._kwargs.get("max_output_tokens") or 4096)
    cmpl_id, created = f"chatcmpl-{uuid.uuid4()}", int(time.time())

    async for token in service.stream(msg, max_tokens):
        chunk = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_id,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"