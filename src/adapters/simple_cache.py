"""
Simple cache adapter - basic in-memory caching implementation.
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime
from core.models import CacheInfo


class SimpleCacheAdapter:
    """Simple in-memory cache implementation."""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, float] = {}
        self._hit_count = 0
        self._miss_count = 0
        self._last_cleanup = datetime.now()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            entry = self._cache[key]
            # Check if expired
            if entry.get('expires_at', float('inf')) > time.time():
                self._hit_count += 1
                return entry['value']
            else:
                # Remove expired entry
                self._remove(key)
        
        self._miss_count += 1
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache with TTL."""
        expires_at = time.time() + ttl
        self._cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'created_at': time.time()
        }
        self._timestamps[key] = time.time()
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if key in self._cache:
            self._remove(key)
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._timestamps.clear()
        self._hit_count = 0
        self._miss_count = 0
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed."""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self._cache.items():
            if entry.get('expires_at', float('inf')) <= current_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            self._remove(key)
        
        self._last_cleanup = datetime.now()
        return len(expired_keys)
    
    def get_info(self) -> CacheInfo:
        """Get cache statistics."""
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0
        
        total_size = sum(len(str(entry)) for entry in self._cache.values())
        
        return CacheInfo(
            size=total_size,
            entries=len(self._cache),
            hit_rate=hit_rate,
            last_cleanup=self._last_cleanup.isoformat()
        )
    
    def _remove(self, key: str) -> None:
        """Internal method to remove key."""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)