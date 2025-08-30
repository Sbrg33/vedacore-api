#!/usr/bin/env python3
"""
Supabase Integration for Enhanced KP Signals History Tracking

Features:
- Historical signal performance tracking
- Signal accuracy backtesting metrics
- User signal preferences and custom alerts
- Batch operations for high-frequency data
- Connection pooling and retry logic
- Enterprise-grade error handling and monitoring
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import asyncpg
import json

logger = logging.getLogger(__name__)

@dataclass 
class SignalHistory:
    """Historical signal record"""
    id: Optional[str] = None
    tenant_id: str = ""
    date: str = ""
    timeframe: str = ""
    planet_id: int = 0
    signal_type: str = ""
    strength: float = 0.0
    direction: str = ""
    actual_outcome: Optional[str] = None
    accuracy_score: Optional[float] = None
    created_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ConfluenceHistory:
    """Historical confluence event record"""
    id: Optional[str] = None
    tenant_id: str = ""
    timestamp: datetime = None
    strength: float = 0.0
    signal_count: int = 0
    timeframes: List[str] = None
    planets: List[int] = None
    direction: str = ""
    outcome: Optional[str] = None
    accuracy_score: Optional[float] = None
    created_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class UserSignalPreferences:
    """User preferences for signal alerts and filtering"""
    tenant_id: str = ""
    timeframes: List[str] = None
    planet_ids: List[int] = None
    min_signal_strength: float = 50.0
    min_confluence_strength: float = 70.0
    alert_methods: List[str] = None  # email, webhook, stream
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SupabaseSignalsService:
    """
    Supabase service for enhanced KP signals history and preferences
    """
    
    def __init__(self):
        self.connection_string = os.getenv("SUPABASE_DATABASE_URL")
        if not self.connection_string:
            logger.warning("SUPABASE_DATABASE_URL not set - Supabase integration disabled")
            self.enabled = False
            return
            
        self.enabled = True
        self.pool: Optional[asyncpg.Pool] = None
        self.max_connections = int(os.getenv("SUPABASE_MAX_CONNECTIONS", "20"))
        self.min_connections = int(os.getenv("SUPABASE_MIN_CONNECTIONS", "5"))
        
        # Performance tracking
        self.query_stats = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "avg_query_time_ms": 0.0,
            "connection_errors": 0
        }
        
        logger.info("Supabase signals service initialized")
    
    async def initialize(self):
        """Initialize connection pool"""
        if not self.enabled:
            return
            
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=self.min_connections,
                max_size=self.max_connections,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                command_timeout=60
            )
            
            # Test connection and create tables if needed
            await self._ensure_tables()
            logger.info(f"Supabase connection pool created: {self.min_connections}-{self.max_connections}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Supabase connection pool: {e}")
            self.enabled = False
            raise
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Supabase connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection with error handling"""
        if not self.enabled or not self.pool:
            raise Exception("Supabase service not available")
            
        connection = None
        try:
            connection = await self.pool.acquire()
            yield connection
        except Exception as e:
            self.query_stats["connection_errors"] += 1
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if connection:
                await self.pool.release(connection)
    
    async def _ensure_tables(self):
        """Create required tables if they don't exist"""
        if not self.enabled:
            return
            
        create_tables_sql = """
        -- Signal history table
        CREATE TABLE IF NOT EXISTS kp_signal_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id TEXT NOT NULL,
            date DATE NOT NULL,
            timeframe TEXT NOT NULL,
            planet_id INTEGER NOT NULL,
            signal_type TEXT NOT NULL,
            strength DECIMAL(5,2) NOT NULL,
            direction TEXT NOT NULL,
            actual_outcome TEXT,
            accuracy_score DECIMAL(5,2),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            metadata JSONB,
            INDEX CONCURRENTLY IF NOT EXISTS idx_signal_history_tenant_date ON kp_signal_history(tenant_id, date),
            INDEX CONCURRENTLY IF NOT EXISTS idx_signal_history_planet_timeframe ON kp_signal_history(planet_id, timeframe)
        );

        -- Confluence history table  
        CREATE TABLE IF NOT EXISTS kp_confluence_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            strength DECIMAL(5,2) NOT NULL,
            signal_count INTEGER NOT NULL,
            timeframes TEXT[] NOT NULL,
            planets INTEGER[] NOT NULL,
            direction TEXT NOT NULL,
            outcome TEXT,
            accuracy_score DECIMAL(5,2),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            metadata JSONB,
            INDEX CONCURRENTLY IF NOT EXISTS idx_confluence_history_tenant ON kp_confluence_history(tenant_id),
            INDEX CONCURRENTLY IF NOT EXISTS idx_confluence_history_timestamp ON kp_confluence_history(timestamp)
        );

        -- User signal preferences table
        CREATE TABLE IF NOT EXISTS kp_user_signal_preferences (
            tenant_id TEXT PRIMARY KEY,
            timeframes TEXT[] NOT NULL DEFAULT '{1m,5m,15m,1h}',
            planet_ids INTEGER[] NOT NULL DEFAULT '{2}',
            min_signal_strength DECIMAL(5,2) NOT NULL DEFAULT 50.0,
            min_confluence_strength DECIMAL(5,2) NOT NULL DEFAULT 70.0,
            alert_methods TEXT[] NOT NULL DEFAULT '{stream}',
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        -- Signal performance summary table (materialized view)
        CREATE TABLE IF NOT EXISTS kp_signal_performance_summary (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id TEXT NOT NULL,
            date DATE NOT NULL,
            timeframe TEXT NOT NULL,
            planet_id INTEGER NOT NULL,
            total_signals INTEGER NOT NULL,
            accurate_signals INTEGER NOT NULL,
            accuracy_rate DECIMAL(5,2) NOT NULL,
            avg_strength DECIMAL(5,2) NOT NULL,
            best_direction TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(tenant_id, date, timeframe, planet_id)
        );
        """
        
        async with self.get_connection() as conn:
            await conn.execute(create_tables_sql)
            logger.info("Supabase tables ensured")
    
    async def record_signal_history(self, 
                                  tenant_id: str,
                                  signals: List[Dict[str, Any]]) -> int:
        """
        Record multiple signals to history table
        
        Args:
            tenant_id: Tenant identifier
            signals: List of signal dictionaries
            
        Returns:
            Number of signals recorded
        """
        if not self.enabled or not signals:
            return 0
            
        start_time = time.time()
        self.query_stats["total_queries"] += 1
        
        try:
            async with self.get_connection() as conn:
                # Prepare batch insert
                insert_sql = """
                INSERT INTO kp_signal_history 
                (tenant_id, date, timeframe, planet_id, signal_type, strength, direction, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """
                
                # Prepare data for batch insert
                batch_data = []
                for signal in signals:
                    batch_data.append((
                        tenant_id,
                        signal.get("date", datetime.utcnow().date()),
                        signal.get("timeframe", "1m"),
                        signal.get("planet_id", 2),
                        signal.get("signal_type", "unknown"),
                        float(signal.get("strength", 0.0)),
                        signal.get("direction", "neutral"),
                        json.dumps(signal.get("metadata", {}))
                    ))
                
                # Execute batch insert
                await conn.executemany(insert_sql, batch_data)
                
                self.query_stats["successful_queries"] += 1
                
                # Update query time stats
                query_time_ms = (time.time() - start_time) * 1000
                total_queries = self.query_stats["successful_queries"]
                current_avg = self.query_stats["avg_query_time_ms"]
                self.query_stats["avg_query_time_ms"] = (
                    (current_avg * (total_queries - 1) + query_time_ms) / total_queries
                )
                
                logger.debug(f"Recorded {len(signals)} signals for tenant {tenant_id}")
                return len(signals)
                
        except Exception as e:
            self.query_stats["failed_queries"] += 1
            logger.error(f"Failed to record signal history: {e}")
            return 0
    
    async def record_confluence_history(self, 
                                      tenant_id: str,
                                      confluence_events: List[Dict[str, Any]]) -> int:
        """
        Record confluence events to history
        
        Args:
            tenant_id: Tenant identifier  
            confluence_events: List of confluence event dictionaries
            
        Returns:
            Number of events recorded
        """
        if not self.enabled or not confluence_events:
            return 0
            
        self.query_stats["total_queries"] += 1
        
        try:
            async with self.get_connection() as conn:
                insert_sql = """
                INSERT INTO kp_confluence_history
                (tenant_id, timestamp, strength, signal_count, timeframes, planets, direction, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """
                
                batch_data = []
                for event in confluence_events:
                    batch_data.append((
                        tenant_id,
                        datetime.fromisoformat(event.get("timestamp", datetime.utcnow().isoformat())),
                        float(event.get("strength", 0.0)),
                        int(event.get("signal_count", 0)),
                        event.get("timeframes", []),
                        event.get("planets", []),
                        event.get("direction", "neutral"),
                        json.dumps(event.get("metadata", {}))
                    ))
                
                await conn.executemany(insert_sql, batch_data)
                self.query_stats["successful_queries"] += 1
                
                logger.debug(f"Recorded {len(confluence_events)} confluence events for tenant {tenant_id}")
                return len(confluence_events)
                
        except Exception as e:
            self.query_stats["failed_queries"] += 1
            logger.error(f"Failed to record confluence history: {e}")
            return 0
    
    async def get_signal_performance_summary(self, 
                                           tenant_id: str,
                                           start_date: datetime,
                                           end_date: datetime,
                                           timeframe: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get signal performance summary for a date range
        
        Args:
            tenant_id: Tenant identifier
            start_date: Start date for analysis
            end_date: End date for analysis
            timeframe: Optional timeframe filter
            
        Returns:
            List of performance summary records
        """
        if not self.enabled:
            return []
            
        self.query_stats["total_queries"] += 1
        
        try:
            async with self.get_connection() as conn:
                where_clause = "WHERE tenant_id = $1 AND date BETWEEN $2 AND $3"
                params = [tenant_id, start_date.date(), end_date.date()]
                
                if timeframe:
                    where_clause += " AND timeframe = $4"
                    params.append(timeframe)
                
                query = f"""
                SELECT 
                    date,
                    timeframe,
                    planet_id,
                    COUNT(*) as total_signals,
                    COUNT(CASE WHEN accuracy_score > 0.6 THEN 1 END) as accurate_signals,
                    ROUND(AVG(CASE WHEN accuracy_score > 0.6 THEN 100.0 ELSE 0.0 END), 2) as accuracy_rate,
                    ROUND(AVG(strength), 2) as avg_strength,
                    MODE() WITHIN GROUP (ORDER BY direction) as best_direction
                FROM kp_signal_history 
                {where_clause}
                GROUP BY date, timeframe, planet_id
                ORDER BY date DESC, timeframe, planet_id
                """
                
                rows = await conn.fetch(query, *params)
                self.query_stats["successful_queries"] += 1
                
                results = []
                for row in rows:
                    results.append({
                        "date": row["date"].isoformat(),
                        "timeframe": row["timeframe"],
                        "planet_id": row["planet_id"],
                        "total_signals": row["total_signals"],
                        "accurate_signals": row["accurate_signals"],
                        "accuracy_rate": float(row["accuracy_rate"] or 0.0),
                        "avg_strength": float(row["avg_strength"] or 0.0),
                        "best_direction": row["best_direction"]
                    })
                
                return results
                
        except Exception as e:
            self.query_stats["failed_queries"] += 1
            logger.error(f"Failed to get signal performance summary: {e}")
            return []
    
    async def get_user_preferences(self, tenant_id: str) -> Optional[UserSignalPreferences]:
        """
        Get user signal preferences
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            User preferences or None if not found
        """
        if not self.enabled:
            return None
            
        self.query_stats["total_queries"] += 1
        
        try:
            async with self.get_connection() as conn:
                query = """
                SELECT * FROM kp_user_signal_preferences WHERE tenant_id = $1
                """
                
                row = await conn.fetchrow(query, tenant_id)
                self.query_stats["successful_queries"] += 1
                
                if row:
                    return UserSignalPreferences(
                        tenant_id=row["tenant_id"],
                        timeframes=row["timeframes"],
                        planet_ids=row["planet_ids"],
                        min_signal_strength=float(row["min_signal_strength"]),
                        min_confluence_strength=float(row["min_confluence_strength"]),
                        alert_methods=row["alert_methods"],
                        active=row["active"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"]
                    )
                    
                return None
                
        except Exception as e:
            self.query_stats["failed_queries"] += 1
            logger.error(f"Failed to get user preferences: {e}")
            return None
    
    async def update_user_preferences(self, 
                                    tenant_id: str, 
                                    preferences: UserSignalPreferences) -> bool:
        """
        Update or create user signal preferences
        
        Args:
            tenant_id: Tenant identifier
            preferences: User preferences object
            
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
            
        self.query_stats["total_queries"] += 1
        
        try:
            async with self.get_connection() as conn:
                query = """
                INSERT INTO kp_user_signal_preferences 
                (tenant_id, timeframes, planet_ids, min_signal_strength, 
                 min_confluence_strength, alert_methods, active)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    timeframes = EXCLUDED.timeframes,
                    planet_ids = EXCLUDED.planet_ids,
                    min_signal_strength = EXCLUDED.min_signal_strength,
                    min_confluence_strength = EXCLUDED.min_confluence_strength,
                    alert_methods = EXCLUDED.alert_methods,
                    active = EXCLUDED.active,
                    updated_at = NOW()
                """
                
                await conn.execute(
                    query,
                    tenant_id,
                    preferences.timeframes,
                    preferences.planet_ids,
                    preferences.min_signal_strength,
                    preferences.min_confluence_strength,
                    preferences.alert_methods,
                    preferences.active
                )
                
                self.query_stats["successful_queries"] += 1
                logger.debug(f"Updated preferences for tenant {tenant_id}")
                return True
                
        except Exception as e:
            self.query_stats["failed_queries"] += 1
            logger.error(f"Failed to update user preferences: {e}")
            return False
    
    async def cleanup_old_records(self, 
                                retention_days: int = 90) -> Tuple[int, int]:
        """
        Clean up old signal and confluence history records
        
        Args:
            retention_days: Number of days to retain records
            
        Returns:
            Tuple of (signals_deleted, confluence_events_deleted)
        """
        if not self.enabled:
            return (0, 0)
            
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        try:
            async with self.get_connection() as conn:
                # Delete old signal history
                signal_result = await conn.execute(
                    "DELETE FROM kp_signal_history WHERE created_at < $1",
                    cutoff_date
                )
                
                # Delete old confluence history
                confluence_result = await conn.execute(
                    "DELETE FROM kp_confluence_history WHERE created_at < $1", 
                    cutoff_date
                )
                
                signals_deleted = int(signal_result.split()[-1])
                confluence_deleted = int(confluence_result.split()[-1])
                
                logger.info(
                    f"Cleanup completed: {signals_deleted} signals, "
                    f"{confluence_deleted} confluence events deleted"
                )
                
                return (signals_deleted, confluence_deleted)
                
        except Exception as e:
            logger.error(f"Failed to cleanup old records: {e}")
            return (0, 0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            **self.query_stats,
            "enabled": self.enabled,
            "pool_size": self.pool.get_size() if self.pool else 0,
            "pool_idle": self.pool.get_idle_size() if self.pool else 0
        }

# Global service instance
supabase_signals_service = SupabaseSignalsService()

async def get_supabase_signals_service() -> SupabaseSignalsService:
    """Get the global Supabase signals service instance"""
    if supabase_signals_service.enabled and not supabase_signals_service.pool:
        await supabase_signals_service.initialize()
    return supabase_signals_service