"""
智谱AI服务模块 - 提供图像识别功能
"""

import os
import json
import base64
import logging
import requests
from typing import Optional, Dict, Any
from config import SERVICE_CONFIG

logger = logging.getLogger('ZHIPU_SERVICE')

class ZhipuAIService:
    def __init__(self):
        """初始化智谱AI服务"""
        self.api_key = os.getenv('ZHIPU_API_KEY')
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        # 优先使用 ZHIPU_API_TIMEOUT 环境变量，其次使用 SERVICE_CONFIG['zhipu_api_timeout']，默认 60s
        try:
            self.timeout = int(os.getenv('ZHIPU_API_TIMEOUT', str(SERVICE_CONFIG.get('zhipu_api_timeout', 60))))
        except Exception:
            self.timeout = 60

        if not self.api_key:
            logger.warning("[ZHIPU] API key not found in environment variables")

        # 允许通过环境变量或配置指定视觉模型（默认使用免费档）
        self.default_vision_model = (
            os.getenv('ZHIPU_VISION_MODEL')
            or SERVICE_CONFIG.get('zhipu_vision_model')
            or 'glm-4.1v-thinking-flash'
        )

    def _resolve_model(self, preferred: Optional[str] = None) -> str:
        """解析要使用的模型，支持外部配置覆盖"""
        return preferred or self.default_vision_model

    def _encode_image(self, image_path: str) -> Optional[str]:
        """
        将图像文件编码为base64
        
        Args:
            image_path (str): 图像文件路径
            
        Returns:
            Optional[str]: base64编码的图像数据，失败时返回None
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"[ZHIPU] Image file not found: {image_path}")
                return None
            
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_image
        except Exception as e:
            logger.error(f"[ZHIPU] Error encoding image {image_path}: {e}")
            return None
    
    def _make_api_request(self, payload: Dict[str, Any]) -> Optional[Dict]:
        """
        发送API请求到智谱AI（带轻量重试）

        Args:
            payload (Dict[str, Any]): 请求载荷

        Returns:
            Optional[Dict]: API响应，失败时返回None或包含错误信息的字典
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}/chat/completions"

        attempts = 0
        max_attempts = 2  # 轻量重试1次
        last_error = None

        while attempts < max_attempts:
            try:
                attempts += 1
                logger.info(f"[ZHIPU] Sending request to {url} with model: {payload.get('model', 'unknown')} (attempt {attempts}/{max_attempts})")
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info("[ZHIPU] API request successful")
                    return result
                elif response.status_code == 429 and attempts < max_attempts:
                    # 简单退避（如果提供了 Retry-After 则遵循）
                    retry_after = response.headers.get('Retry-After')
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else 2
                    logger.warning(f"[ZHIPU] Rate limited (429). Retrying after {delay}s...")
                    import time as _t
                    _t.sleep(delay)
                    continue
                else:
                    error_text = response.text
                    logger.error(f"[ZHIPU] API request failed with status {response.status_code}: {error_text}")
                    try:
                        error_json = response.json()
                        return {"error": error_json}
                    except:
                        return {"error": {"code": response.status_code, "message": error_text}}

            except requests.exceptions.Timeout:
                last_error = {"code": "timeout", "message": f"Request timed out after {self.timeout}s"}
                logger.error(f"[ZHIPU] API request timed out after {self.timeout}s")
                if attempts >= max_attempts:
                    return {"error": last_error}
            except requests.exceptions.ConnectionError as e:
                last_error = {"code": "connection_error", "message": f"Connection failed: {str(e)}"}
                logger.error(f"[ZHIPU] Connection error: {e}")
                if attempts >= max_attempts:
                    return {"error": last_error}
            except requests.exceptions.RequestException as e:
                last_error = {"code": "request_error", "message": str(e)}
                logger.error(f"[ZHIPU] API request failed: {e}")
                if attempts >= max_attempts:
                    return {"error": last_error}
            except Exception as e:
                last_error = {"code": "unexpected_error", "message": str(e)}
                logger.error(f"[ZHIPU] Unexpected error during API request: {e}")
                if attempts >= max_attempts:
                    return {"error": last_error}

        # 理论上不会到达这里
        return {"error": last_error or {"code": "unknown", "message": "Unknown error"}}

    def recognize_image(self, image_path: str, prompt: str = "请描述这张图片") -> Optional[Dict]:
        """
        识别图像内容
        
        Args:
            image_path (str): 图像文件路径
            prompt (str): 提示词，默认为"请描述这张图片"
            
        Returns:
            Optional[Dict]: 识别结果，失败时返回None
        """
        try:
            # 检查API密钥
            if not self.api_key:
                logger.error("[ZHIPU] API key not configured")
                return {"success": False, "error": "API key not configured"}
            
            # 编码图像
            encoded_image = self._encode_image(image_path)
            if not encoded_image:
                # 更具体的错误分类：不存在 vs. 无法读取/损坏
                if not os.path.exists(image_path):
                    return {"success": False, "error": f"Image file not found: {image_path}", "code": "file_not_found"}
                return {"success": False, "error": "Failed to encode image (file unreadable or corrupted)", "code": "encode_failed"}

            # 构建请求载荷
            payload = {
                "model": self._resolve_model("glm-4.1v-thinking-flash"),  # 优先使用免费视觉模型，如不可用由健康检查回退
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_image}"
                                }
                            }
                        ]
                    }
                ],
                "stream": False
            }
            
            # 发送API请求
            response = self._make_api_request(payload)
            if not response:
                return {"success": False, "error": "API request failed"}
            
            # 解析响应
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"]
                return {
                    "success": True,
                    "data": {
                        "description": content,
                        "model": payload.get("model"),
                        "usage": response.get("usage", {})
                    }
                }
            elif "error" in response:
                err = response["error"]
                code = err.get("code")
                msg = err.get("message") or str(err)
                # 针对 1113（余额不足/无资源包）与 429（限流）提供友好提示
                if code in ("1113", 1113) or code == 429:
                    logger.error(f"[ZHIPU] API quota or credit issue: {msg}")
                    return {"success": False, "error": "ZhipuAI credits/quota exhausted or unavailable. Please check plan or switch to free model.", "code": code}
                return {"success": False, "error": msg, "code": code}
            else:
                logger.error("[ZHIPU] Unexpected API response format")
                return {"success": False, "error": "Unexpected API response format"}

        except Exception as e:
            logger.error(f"[ZHIPU] Error recognizing image: {e}")
            return {"success": False, "error": str(e)}
    
    def check_service_health(self) -> Dict:
        """
        检查服务健康状态

        Returns:
            Dict: 服务健康状态信息
        """
        try:
            if not self.api_key:
                return {
                    "success": False,
                    "status": "API key not configured",
                    "details": "Please set ZHIPU_API_KEY environment variable"
                }

            # 尝试多个模型进行健康检查
            models_to_test = [
                "glm-4.1v-thinking-flash",  # 免费模型
                "glm-4",                    # 标准模型
                "glm-4-flash"              # 快速模型
            ]

            last_error = None
            for model in models_to_test:
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Hi"
                            }
                        ],
                        "max_tokens": 5,
                        "stream": False
                    }

                    logger.info(f"[ZHIPU] Testing model: {model}")
                    response = self._make_api_request(payload)

                    if response and "choices" in response:
                        return {
                            "success": True,
                            "status": "Healthy",
                            "model_used": model,
                            "details": f"Successfully connected using model {model}"
                        }
                    elif response and "error" in response:
                        last_error = response["error"]
                        logger.warning(f"[ZHIPU] Model {model} failed: {last_error}")
                        continue
                    else:
                        last_error = "Unknown API response format"
                        continue

                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[ZHIPU] Model {model} exception: {e}")
                    continue

            # 所有模型都失败了
            return {
                "success": False,
                "status": "All models failed",
                "details": f"Last error: {last_error}",
                "tested_models": models_to_test
            }

        except Exception as e:
            logger.error(f"[ZHIPU] Health check failed: {e}")
            return {
                "success": False,
                "status": f"Health check exception: {str(e)}",
                "details": "Unexpected error during health check"
            }
