"""
Health check system for RememBot.
Provides HTTP endpoints for monitoring service health.
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aiohttp import web, ClientSession
from aiohttp.web import Application, Response, Request

from .config import get_config
from .database import DatabaseManager

logger = logging.getLogger(__name__)


class HealthChecker:
    """Health check service for RememBot."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize health checker."""
        self.db_manager = db_manager
        self.app = None
        self.runner = None
        self.site = None
        self.start_time = time.time()
        self.last_check = None
        self.health_status = {}
    
    async def start(self):
        """Start the health check service."""
        config = get_config()
        
        if not config.health_check_enabled:
            logger.info("Health check service disabled")
            return
        
        try:
            self.app = Application()
            self.app.router.add_get('/health', self.health_endpoint)
            self.app.router.add_get('/health/detailed', self.detailed_health_endpoint)
            self.app.router.add_get('/metrics', self.metrics_endpoint)
            
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, 'localhost', config.health_check_port)
            await self.site.start()
            
            logger.info(f"Health check service started on port {config.health_check_port}")
            
        except Exception as e:
            logger.error(f"Failed to start health check service: {e}")
            raise
    
    async def stop(self):
        """Stop the health check service."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("Health check service stopped")
    
    async def health_endpoint(self, request: Request) -> Response:
        """Basic health check endpoint."""
        try:
            health_data = await self._check_basic_health()
            status_code = 200 if health_data['status'] == 'healthy' else 503
            
            return Response(
                text=json.dumps(health_data, indent=2),
                status=status_code,
                content_type='application/json'
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return Response(
                text=json.dumps({
                    'status': 'error',
                    'message': str(e),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }),
                status=503,
                content_type='application/json'
            )
    
    async def detailed_health_endpoint(self, request: Request) -> Response:
        """Detailed health check endpoint."""
        try:
            health_data = await self._check_detailed_health()
            status_code = 200 if health_data['status'] == 'healthy' else 503
            
            return Response(
                text=json.dumps(health_data, indent=2),
                status=status_code,
                content_type='application/json'
            )
        except Exception as e:
            logger.error(f"Detailed health check failed: {e}")
            return Response(
                text=json.dumps({
                    'status': 'error',
                    'message': str(e),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }),
                status=503,
                content_type='application/json'
            )
    
    async def metrics_endpoint(self, request: Request) -> Response:
        """Metrics endpoint for monitoring."""
        try:
            metrics_data = await self._get_metrics()
            
            return Response(
                text=json.dumps(metrics_data, indent=2),
                status=200,
                content_type='application/json'
            )
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return Response(
                text=json.dumps({
                    'error': str(e),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }),
                status=500,
                content_type='application/json'
            )
    
    async def _check_basic_health(self) -> Dict[str, Any]:
        """Perform basic health checks."""
        checks = {}
        overall_status = 'healthy'
        
        # Database connectivity check
        try:
            await self.db_manager._get_connection()
            checks['database'] = {
                'status': 'healthy',
                'message': 'Database connection successful'
            }
        except Exception as e:
            checks['database'] = {
                'status': 'unhealthy',
                'message': f'Database connection failed: {e}'
            }
            overall_status = 'unhealthy'
        
        # Configuration check
        try:
            config = get_config()
            checks['configuration'] = {
                'status': 'healthy',
                'message': 'Configuration loaded successfully'
            }
        except Exception as e:
            checks['configuration'] = {
                'status': 'unhealthy',
                'message': f'Configuration error: {e}'
            }
            overall_status = 'unhealthy'
        
        self.last_check = datetime.now(timezone.utc)
        self.health_status = {
            'status': overall_status,
            'checks': checks,
            'timestamp': self.last_check.isoformat(),
            'uptime_seconds': time.time() - self.start_time
        }
        
        return self.health_status
    
    async def _check_detailed_health(self) -> Dict[str, Any]:
        """Perform detailed health checks."""
        basic_health = await self._check_basic_health()
        
        # Add detailed checks
        detailed_checks = {}
        
        # Database detailed check
        try:
            # Test database operations
            start_time = time.time()
            test_stats = await self.db_manager.get_user_stats(0)  # Test query
            query_time = time.time() - start_time
            
            detailed_checks['database_performance'] = {
                'status': 'healthy',
                'query_time_ms': round(query_time * 1000, 2),
                'message': f'Database query completed in {query_time:.3f}s'
            }
        except Exception as e:
            detailed_checks['database_performance'] = {
                'status': 'unhealthy',
                'message': f'Database performance test failed: {e}'
            }
            basic_health['status'] = 'unhealthy'
        
        # Memory and resource checks
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            detailed_checks['resources'] = {
                'status': 'healthy',
                'memory_mb': round(memory_info.rss / 1024 / 1024, 2),
                'cpu_percent': process.cpu_percent(),
                'num_threads': process.num_threads()
            }
        except ImportError:
            detailed_checks['resources'] = {
                'status': 'info',
                'message': 'psutil not available for resource monitoring'
            }
        except Exception as e:
            detailed_checks['resources'] = {
                'status': 'warning',
                'message': f'Resource monitoring failed: {e}'
            }
        
        # AI service connectivity check
        config = get_config()
        if config.openai_api_key or config.openrouter_api_key:
            try:
                # Test AI service connectivity
                detailed_checks['ai_services'] = await self._check_ai_services(config)
            except Exception as e:
                detailed_checks['ai_services'] = {
                    'status': 'warning',
                    'message': f'AI service check failed: {e}'
                }
        else:
            detailed_checks['ai_services'] = {
                'status': 'info',
                'message': 'No AI API keys configured'
            }
        
        # Combine basic and detailed checks
        basic_health['detailed_checks'] = detailed_checks
        return basic_health
    
    async def _check_ai_services(self, config) -> Dict[str, Any]:
        """Check AI service connectivity."""
        if config.openai_api_key:
            return await self._check_openai_service(config.openai_api_key)
        elif config.openrouter_api_key:
            return await self._check_openrouter_service(config.openrouter_api_key)
        else:
            return {
                'status': 'info',
                'message': 'No AI services configured'
            }
    
    async def _check_openai_service(self, api_key: str) -> Dict[str, Any]:
        """Check OpenAI API connectivity."""
        try:
            async with ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                }
                
                async with session.get(
                    'https://api.openai.com/v1/models',
                    headers=headers,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        return {
                            'status': 'healthy',
                            'service': 'openai',
                            'message': 'OpenAI API accessible'
                        }
                    else:
                        return {
                            'status': 'unhealthy',
                            'service': 'openai',
                            'message': f'OpenAI API returned status {response.status}'
                        }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'service': 'openai',
                'message': f'OpenAI API check failed: {e}'
            }
    
    async def _check_openrouter_service(self, api_key: str) -> Dict[str, Any]:
        """Check OpenRouter API connectivity."""
        try:
            async with ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                }
                
                async with session.get(
                    'https://openrouter.ai/api/v1/models',
                    headers=headers,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        return {
                            'status': 'healthy',
                            'service': 'openrouter',
                            'message': 'OpenRouter API accessible'
                        }
                    else:
                        return {
                            'status': 'unhealthy',
                            'service': 'openrouter',
                            'message': f'OpenRouter API returned status {response.status}'
                        }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'service': 'openrouter',
                'message': f'OpenRouter API check failed: {e}'
            }
    
    async def _get_metrics(self) -> Dict[str, Any]:
        """Get system metrics."""
        metrics = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': time.time() - self.start_time,
            'last_health_check': self.last_check.isoformat() if self.last_check else None
        }
        
        # Database metrics
        try:
            # Get some basic database stats
            # Note: This would need to be implemented in DatabaseManager
            metrics['database'] = {
                'status': 'available',
                'last_query_time': None  # Would track query performance
            }
        except Exception as e:
            metrics['database'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # System metrics (if psutil available)
        try:
            import psutil
            process = psutil.Process()
            
            metrics['system'] = {
                'memory_mb': round(process.memory_info().rss / 1024 / 1024, 2),
                'cpu_percent': process.cpu_percent(),
                'num_threads': process.num_threads(),
                'open_files': len(process.open_files()) if hasattr(process, 'open_files') else None
            }
        except ImportError:
            metrics['system'] = {'status': 'psutil_not_available'}
        except Exception as e:
            metrics['system'] = {'error': str(e)}
        
        return metrics