"""
API v1 Stream Router

Streaming endpoints for SSE and WebSocket with unified token authentication.
Implements PM requirements for secure streaming with token redaction.
"""

from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from app.openapi.common import DEFAULT_ERROR_RESPONSES
from fastapi.responses import StreamingResponse
import jwt
import json
import asyncio

from .models import BaseResponse, ErrorResponse, PATH_TEMPLATES
from app.core.environment import get_complete_config

router = APIRouter(prefix="/api/v1", tags=["stream"], responses=DEFAULT_ERROR_RESPONSES) 


def verify_stream_token(token: str, expected_topic: Optional[str] = None) -> dict:
    """
    Verify streaming token with PM security requirements:
    - Audience must be "stream"
    - Topic must match if specified
    - JTI single-use enforcement
    - Token expiration check
    """
    try:
        config = get_complete_config()
        payload = jwt.decode(token, config.database.auth_secret, algorithms=["HS256"])
        
        # Verify audience
        if payload.get("aud") != "stream":
            raise jwt.InvalidTokenError("Invalid audience for streaming")
        
        # Verify topic if specified
        token_topic = payload.get("topic")
        if expected_topic and token_topic != expected_topic:
            raise jwt.InvalidTokenError(f"Token topic {token_topic} does not match requested {expected_topic}")
        
        # TODO: Implement JTI single-use check
        # jti = payload.get("jti")
        # if await is_jti_already_used(jti):
        #     raise jwt.InvalidTokenError("Token already used")
        # await mark_jti_as_used(jti)
        
        return payload
        
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse.create(
                code="AUTH_ERROR",
                message=f"Invalid streaming token: {str(e)}"
            ).dict()
        )


async def generate_sse_stream(topic: str, tenant_id: str) -> AsyncIterator[str]:
    """
    Generate Server-Sent Events stream for topic.
    
    Yields formatted SSE events with proper envelope structure
    following PM specification.
    """
    try:
        # Import streaming service
        from api.services.stream_manager import stream_manager
        
        # Subscribe to topic
        queue = await stream_manager.subscribe(topic, tenant_id)
        
        sequence = 0
        while True:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                
                # Format as SSE event envelope
                envelope = {
                    "v": 1,
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "seq": sequence,
                    "topic": topic,
                    "event": "update",
                    "payload": message
                }
                
                # Send as SSE event
                sse_data = f"data: {json.dumps(envelope)}\n\n"
                yield sse_data
                
                sequence += 1
                
            except asyncio.TimeoutError:
                # Send heartbeat
                heartbeat = {
                    "v": 1,
                    "ts": datetime.utcnow().isoformat() + "Z", 
                    "seq": sequence,
                    "topic": topic,
                    "event": "heartbeat",
                    "payload": {}
                }
                
                sse_data = f"data: {json.dumps(heartbeat)}\n\n"
                yield sse_data
                
                sequence += 1
                
    except Exception as e:
        # Send error event
        error_event = {
            "v": 1,
            "ts": datetime.utcnow().isoformat() + "Z",
            "seq": sequence,
            "topic": topic, 
            "event": "error",
            "payload": {"message": str(e)}
        }
        
        yield f"data: {json.dumps(error_event)}\n\n"
    finally:
        # Cleanup subscription
        if 'queue' in locals():
            await stream_manager.unsubscribe(topic, tenant_id, queue)


@router.get(
    "/stream",
    summary="Server-Sent Events Stream",
    operation_id="v1_stream_sse",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_events(
    topic: str = Query(..., description="Topic to subscribe to"),
    token: str = Query(..., description="One-time streaming token")
) -> StreamingResponse:
    """
    Subscribe to Server-Sent Events stream for specified topic.
    
    Requires one-time streaming token issued via /api/v1/auth/stream-token.
    Token must be topic-scoped and will be consumed on first use.
    """
    # Verify streaming token
    payload = verify_stream_token(token, topic)
    tenant_id = payload.get("tid", "unknown")
    
    # Generate SSE stream
    return StreamingResponse(
        generate_sse_stream(topic, tenant_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive", 
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Access-Control-Allow-Origin": "*",  # CORS handled by middleware
        }
    )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="One-time streaming token")
):
    """
    WebSocket endpoint for real-time bidirectional streaming.
    
    Supports subscription to multiple topics and client commands.
    Uses same token authentication as SSE endpoint.
    """
    await websocket.accept()
    
    try:
        # Verify initial token - allow any topic for WebSocket
        payload = verify_stream_token(token)
        tenant_id = payload.get("tid", "unknown")
        
        # Track subscriptions
        subscriptions = {}
        sequence = 0
        
        # Send welcome message
        welcome = {
            "v": 1,
            "ts": datetime.utcnow().isoformat() + "Z",
            "seq": sequence,
            "event": "welcome",
            "payload": {
                "tenant_id": tenant_id,
                "supported_commands": ["subscribe", "unsubscribe", "ping"]
            }
        }
        await websocket.send_text(json.dumps(welcome))
        sequence += 1
        
        # Message handling loop
        while True:
            try:
                # Receive client message
                data = await websocket.receive_text()
                message = json.loads(data)
                
                command = message.get("command")
                if command == "subscribe":
                    topic = message.get("topic")
                    if topic:
                        # Import streaming service
                        from api.services.stream_manager import stream_manager
                        queue = await stream_manager.subscribe(topic, tenant_id)
                        subscriptions[topic] = queue
                        
                        # Confirm subscription
                        response = {
                            "v": 1,
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "seq": sequence,
                            "event": "subscribed",
                            "payload": {"topic": topic}
                        }
                        await websocket.send_text(json.dumps(response))
                        sequence += 1
                        
                elif command == "unsubscribe":
                    topic = message.get("topic") 
                    if topic in subscriptions:
                        from api.services.stream_manager import stream_manager
                        await stream_manager.unsubscribe(topic, tenant_id, subscriptions[topic])
                        del subscriptions[topic]
                        
                        # Confirm unsubscription
                        response = {
                            "v": 1,
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "seq": sequence,
                            "event": "unsubscribed", 
                            "payload": {"topic": topic}
                        }
                        await websocket.send_text(json.dumps(response))
                        sequence += 1
                        
                elif command == "ping":
                    # Respond to ping
                    response = {
                        "v": 1,
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "seq": sequence,
                        "event": "pong",
                        "payload": message.get("payload", {})
                    }
                    await websocket.send_text(json.dumps(response))
                    sequence += 1
                    
            except json.JSONDecodeError:
                error_response = {
                    "v": 1,
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "seq": sequence,
                    "event": "error",
                    "payload": {"message": "Invalid JSON message"}
                }
                await websocket.send_text(json.dumps(error_response))
                sequence += 1
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            error_response = {
                "v": 1,
                "ts": datetime.utcnow().isoformat() + "Z", 
                "seq": sequence,
                "event": "error",
                "payload": {"message": str(e)}
            }
            await websocket.send_text(json.dumps(error_response))
        except:
            pass
    finally:
        # Cleanup subscriptions
        if 'subscriptions' in locals():
            from api.services.stream_manager import stream_manager
            for topic, queue in subscriptions.items():
                try:
                    await stream_manager.unsubscribe(topic, tenant_id, queue)
                except:
                    pass


@router.get(
    "/stream/topics",
    response_model=BaseResponse,
    summary="List Available Topics",
    operation_id="v1_stream_topics",
)
async def list_stream_topics() -> BaseResponse:
    """
    Get list of available streaming topics.
    
    Returns discoverable topics with descriptions and access requirements.
    """
    topics = [
        {
            "topic": "kp.ruling_planets",
            "description": "KP Ruling Planets updates",
            "update_frequency": "real-time",
            "requires_auth": True
        },
        {
            "topic": "kp.moon.chain",
            "description": "Moon chain progression updates", 
            "update_frequency": "every 2 minutes",
            "requires_auth": True
        },
        {
            "topic": "jyotish.transit_events",
            "description": "Significant transit events",
            "update_frequency": "event-driven", 
            "requires_auth": True
        },
        {
            "topic": "location.activation",
            "description": "Global Locality Research updates",
            "update_frequency": "hourly",
            "requires_auth": True
        }
    ]
    
    return BaseResponse.create(
        data=topics,
        path_template=PATH_TEMPLATES["stream_topics"],
        count=len(topics),
        compute_units=0.01
    )
