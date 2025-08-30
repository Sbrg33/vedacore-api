"""
Token Auditing Service

Implements PM5.txt Section 3 requirement: store token metadata for 30 days.
Provides comprehensive audit trail for security incident investigation.

Features:
- Store jti, sub, tid, topic, iat, exp, region for 30 days
- Queryable by incident time range
- Automatic cleanup with configurable retention
- Performance-optimized with Redis backend
- Security-focused design for incident response
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import json
import hashlib

from api.services.redis_config import get_redis
from app.core.logging import get_api_logger

logger = get_api_logger("token_auditing")


class TokenEventType(Enum):
    """Types of token events to audit."""
    ISSUED = "issued"
    VALIDATED = "validated"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REPLAY_ATTEMPTED = "replay_attempted"
    INVALID_SIGNATURE = "invalid_signature"


@dataclass
class TokenAuditRecord:
    """Token audit record structure per PM5.txt requirements."""
    jti: str                    # PM5.txt: JWT ID for unique identification
    sub: str                    # PM5.txt: Subject (API key ID)
    tid: str                    # PM5.txt: Tenant ID
    topic: Optional[str]        # PM5.txt: Stream topic (for streaming tokens)
    iat: int                    # PM5.txt: Issued at timestamp
    exp: int                    # PM5.txt: Expiration timestamp
    region: Optional[str]       # PM5.txt: Regional binding
    
    # Additional audit fields
    event_type: TokenEventType
    event_timestamp: int
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    success: bool = True
    error_details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenAuditRecord':
        """Create from stored dictionary."""
        data['event_type'] = TokenEventType(data['event_type'])
        return cls(**data)


class TokenAuditingService:
    """Service for token audit trail management."""
    
    def __init__(self):
        self.retention_days = int(os.getenv("TOKEN_AUDIT_RETENTION_DAYS", "30"))
        self.enabled = os.getenv("TOKEN_AUDITING_ENABLED", "true").lower() == "true"
        
        # Redis key patterns
        self.audit_key_prefix = "token_audit"
        self.jti_tracking_prefix = "token_jti"
        self.tenant_index_prefix = "token_tenant_idx"
        self.region_index_prefix = "token_region_idx"
        
        logger.info(f"Token auditing service initialized (enabled: {self.enabled})")
        logger.info(f"Retention period: {self.retention_days} days")
    
    async def record_token_event(
        self,
        token_payload: Dict[str, Any],
        event_type: TokenEventType,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        endpoint: Optional[str] = None,
        success: bool = True,
        error_details: Optional[str] = None
    ) -> bool:
        """Record token event for audit trail."""
        
        if not self.enabled:
            return True
            
        try:
            now = int(datetime.now(timezone.utc).timestamp())
            
            # Create audit record
            audit_record = TokenAuditRecord(
                jti=token_payload.get("jti", "unknown"),
                sub=token_payload.get("sub", "unknown"),
                tid=token_payload.get("tid", "unknown"),
                topic=token_payload.get("topic"),
                iat=token_payload.get("iat", now),
                exp=token_payload.get("exp", now + 3600),
                region=token_payload.get("region"),
                event_type=event_type,
                event_timestamp=now,
                client_ip=self._hash_ip(client_ip) if client_ip else None,
                user_agent=self._truncate_user_agent(user_agent),
                endpoint=endpoint,
                success=success,
                error_details=error_details
            )
            
            # Store in Redis with TTL
            await self._store_audit_record(audit_record)
            
            # Update indexes for efficient querying
            await self._update_audit_indexes(audit_record)
            
            # Track JTI for replay prevention (streaming tokens)
            if event_type == TokenEventType.ISSUED and audit_record.topic:
                await self._track_jti(audit_record)
            
            logger.debug(f"Recorded token event: {event_type.value} for JTI {audit_record.jti}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to record token audit event: {e}")
            return False
    
    async def query_by_incident_timerange(
        self,
        start_time: datetime,
        end_time: datetime,
        tenant_id: Optional[str] = None,
        region: Optional[str] = None,
        event_types: Optional[List[TokenEventType]] = None
    ) -> List[TokenAuditRecord]:
        """Query audit records by incident time range (PM5.txt requirement)."""
        
        if not self.enabled:
            return []
        
        try:
            redis = await get_redis()
            
            start_ts = int(start_time.timestamp())
            end_ts = int(end_time.timestamp())
            
            logger.info(f"Querying token audit records from {start_time} to {end_time}")
            
            # Get all audit keys within time range
            pattern = f"{self.audit_key_prefix}:*"
            audit_keys = await redis.keys(pattern)
            
            records = []
            for key in audit_keys:
                try:
                    data = await redis.hgetall(key)
                    if not data:
                        continue
                        
                    record = TokenAuditRecord.from_dict(data)
                    
                    # Filter by time range
                    if not (start_ts <= record.event_timestamp <= end_ts):
                        continue
                        
                    # Filter by tenant if specified
                    if tenant_id and record.tid != tenant_id:
                        continue
                        
                    # Filter by region if specified
                    if region and record.region != region:
                        continue
                        
                    # Filter by event types if specified
                    if event_types and record.event_type not in event_types:
                        continue
                        
                    records.append(record)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse audit record from key {key}: {e}")
                    continue
            
            # Sort by timestamp
            records.sort(key=lambda r: r.event_timestamp)
            
            logger.info(f"Found {len(records)} audit records matching criteria")
            return records
            
        except Exception as e:
            logger.error(f"Failed to query audit records: {e}")
            return []
    
    async def query_by_tenant(
        self, 
        tenant_id: str, 
        hours_back: int = 24
    ) -> List[TokenAuditRecord]:
        """Query recent audit records for specific tenant."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)
        
        return await self.query_by_incident_timerange(
            start_time=start_time,
            end_time=end_time,
            tenant_id=tenant_id
        )
    
    async def check_jti_used(self, jti: str) -> bool:
        """Check if JTI has been used (replay prevention)."""
        if not self.enabled:
            return False
            
        try:
            redis = await get_redis()
            key = f"{self.jti_tracking_prefix}:{jti}"
            
            exists = await redis.exists(key)
            return bool(exists)
            
        except Exception as e:
            logger.error(f"Failed to check JTI usage: {e}")
            return False
    
    async def mark_jti_used(self, jti: str, ttl_seconds: int = 300) -> bool:
        """Mark JTI as used with TTL."""
        if not self.enabled:
            return True
            
        try:
            redis = await get_redis()
            key = f"{self.jti_tracking_prefix}:{jti}"
            
            await redis.set(key, "used", ex=ttl_seconds)
            logger.debug(f"Marked JTI as used: {jti}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark JTI as used: {e}")
            return False
    
    async def get_audit_statistics(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get audit trail statistics for monitoring."""
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=hours_back)
            
            records = await self.query_by_incident_timerange(start_time, end_time)
            
            # Calculate statistics
            stats = {
                "total_events": len(records),
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": hours_back
                },
                "event_types": {},
                "tenants": {},
                "regions": {},
                "success_rate": 0,
                "error_events": []
            }
            
            successful_events = 0
            for record in records:
                # Count event types
                event_type = record.event_type.value
                stats["event_types"][event_type] = stats["event_types"].get(event_type, 0) + 1
                
                # Count tenants
                stats["tenants"][record.tid] = stats["tenants"].get(record.tid, 0) + 1
                
                # Count regions
                if record.region:
                    stats["regions"][record.region] = stats["regions"].get(record.region, 0) + 1
                
                # Track success rate
                if record.success:
                    successful_events += 1
                else:
                    stats["error_events"].append({
                        "jti": record.jti,
                        "event_type": event_type,
                        "timestamp": record.event_timestamp,
                        "error": record.error_details
                    })
            
            stats["success_rate"] = (successful_events / len(records) * 100) if records else 100
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to calculate audit statistics: {e}")
            return {"error": str(e)}
    
    async def cleanup_expired_records(self) -> int:
        """Clean up audit records older than retention period."""
        if not self.enabled:
            return 0
            
        try:
            redis = await get_redis()
            cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=self.retention_days)).timestamp())
            
            logger.info(f"Cleaning up audit records older than {self.retention_days} days")
            
            pattern = f"{self.audit_key_prefix}:*"
            audit_keys = await redis.keys(pattern)
            
            deleted_count = 0
            for key in audit_keys:
                try:
                    data = await redis.hgetall(key)
                    if not data:
                        continue
                        
                    event_timestamp = int(data.get("event_timestamp", 0))
                    if event_timestamp < cutoff_timestamp:
                        await redis.delete(key)
                        deleted_count += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to check/delete audit record {key}: {e}")
                    continue
            
            logger.info(f"Cleaned up {deleted_count} expired audit records")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired records: {e}")
            return 0
    
    async def _store_audit_record(self, record: TokenAuditRecord) -> bool:
        """Store audit record in Redis with TTL."""
        try:
            redis = await get_redis()
            
            # Create unique key for this audit event
            key = f"{self.audit_key_prefix}:{record.jti}:{record.event_timestamp}"
            
            # Store as hash with TTL
            ttl_seconds = self.retention_days * 24 * 3600
            await redis.hmset(key, record.to_dict())
            await redis.expire(key, ttl_seconds)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store audit record: {e}")
            return False
    
    async def _update_audit_indexes(self, record: TokenAuditRecord) -> bool:
        """Update indexes for efficient querying."""
        try:
            redis = await get_redis()
            
            # Tenant index
            tenant_key = f"{self.tenant_index_prefix}:{record.tid}"
            await redis.sadd(tenant_key, f"{record.jti}:{record.event_timestamp}")
            await redis.expire(tenant_key, self.retention_days * 24 * 3600)
            
            # Region index (if present)
            if record.region:
                region_key = f"{self.region_index_prefix}:{record.region}"
                await redis.sadd(region_key, f"{record.jti}:{record.event_timestamp}")
                await redis.expire(region_key, self.retention_days * 24 * 3600)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update audit indexes: {e}")
            return False
    
    async def _track_jti(self, record: TokenAuditRecord) -> bool:
        """Track JTI for replay prevention."""
        try:
            # Calculate TTL based on token expiration
            ttl = max(300, record.exp - record.iat)  # Minimum 5 minutes
            
            return await self.mark_jti_used(record.jti, ttl)
            
        except Exception as e:
            logger.error(f"Failed to track JTI: {e}")
            return False
    
    def _hash_ip(self, ip: str) -> str:
        """Hash IP address for privacy-compliant storage."""
        # Use SHA-256 hash for privacy while maintaining queryability
        return hashlib.sha256(ip.encode()).hexdigest()[:16]
    
    def _truncate_user_agent(self, user_agent: Optional[str]) -> Optional[str]:
        """Truncate user agent for storage efficiency."""
        if not user_agent:
            return None
        return user_agent[:200]  # Limit to 200 characters


# Global service instance
_audit_service: Optional[TokenAuditingService] = None

async def get_token_audit_service() -> TokenAuditingService:
    """Get token auditing service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = TokenAuditingService()
    return _audit_service


# Convenience functions for common audit operations

async def audit_token_issued(token_payload: Dict, client_ip: str = None, endpoint: str = None):
    """Record token issuance event."""
    service = await get_token_audit_service()
    return await service.record_token_event(
        token_payload=token_payload,
        event_type=TokenEventType.ISSUED,
        client_ip=client_ip,
        endpoint=endpoint
    )


async def audit_token_validated(token_payload: Dict, client_ip: str = None, endpoint: str = None):
    """Record token validation event."""
    service = await get_token_audit_service()
    return await service.record_token_event(
        token_payload=token_payload,
        event_type=TokenEventType.VALIDATED,
        client_ip=client_ip,
        endpoint=endpoint
    )


async def audit_token_replay_attempt(token_payload: Dict, client_ip: str = None, endpoint: str = None):
    """Record token replay attempt (security incident)."""
    service = await get_token_audit_service()
    return await service.record_token_event(
        token_payload=token_payload,
        event_type=TokenEventType.REPLAY_ATTEMPTED,
        client_ip=client_ip,
        endpoint=endpoint,
        success=False,
        error_details="Token replay attempt detected"
    )


async def audit_invalid_token(token_payload: Dict, error: str, client_ip: str = None):
    """Record invalid token event."""
    service = await get_token_audit_service()
    return await service.record_token_event(
        token_payload=token_payload,
        event_type=TokenEventType.INVALID_SIGNATURE,
        client_ip=client_ip,
        success=False,
        error_details=error
    )