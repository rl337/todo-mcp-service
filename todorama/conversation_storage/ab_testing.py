"""AB testing management operations."""

import json
import hashlib
import logging
from typing import Optional, List, Dict, Any
import statistics

logger = logging.getLogger(__name__)


class ABTestingManager:
    """Manages AB testing operations."""
    
    def __init__(self, adapter, normalize_sql_func):
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        return self.adapter.connect()
    
    def create_ab_test(
        self,
        name: str,
        control: Dict[str, Any],
        variant: Dict[str, Any],
        description: Optional[str] = None,
        traffic_split: float = 0.5,
        active: bool = True
    ) -> int:
        """Create an A/B test configuration."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                INSERT INTO ab_tests (name, description, control_config, variant_config, traffic_split, active)
                VALUES (?, ?, ?, ?, ?, ?)
            """)
            cursor.execute(query, (
                name,
                description,
                json.dumps(control),
                json.dumps(variant),
                traffic_split,
                1 if active else 0
            ))
            test_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            logger.info(f"Created A/B test {test_id}: {name}")
            return test_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create A/B test: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_ab_test(self, test_id: int) -> Optional[Dict[str, Any]]:
        """Get an A/B test configuration."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, name, description, control_config, variant_config, 
                       traffic_split, active, created_at, updated_at
                FROM ab_tests
                WHERE id = ?
            """)
            cursor.execute(query, (test_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'control_config': row[3],
                    'variant_config': row[4],
                    'traffic_split': row[5],
                    'active': bool(row[6]),
                    'created_at': row[7],
                    'updated_at': row[8]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get A/B test: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def list_ab_tests(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """List A/B tests."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            where_clause = "WHERE active = 1" if active_only else "1=1"
            query = self._normalize_sql(f"""
                SELECT id, name, description, control_config, variant_config, 
                       traffic_split, active, created_at, updated_at
                FROM ab_tests
                {where_clause}
                ORDER BY created_at DESC
            """)
            cursor.execute(query)
            
            tests = []
            for row in cursor.fetchall():
                tests.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'control_config': row[3],
                    'variant_config': row[4],
                    'traffic_split': row[5],
                    'active': bool(row[6]),
                    'created_at': row[7],
                    'updated_at': row[8]
                })
            return tests
        except Exception as e:
            logger.error(f"Failed to list A/B tests: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def update_ab_test(
        self,
        test_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        control: Optional[Dict[str, Any]] = None,
        variant: Optional[Dict[str, Any]] = None,
        traffic_split: Optional[float] = None,
        active: Optional[bool] = None
    ) -> bool:
        """Update an A/B test configuration."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if control is not None:
                updates.append("control_config = ?")
                params.append(json.dumps(control))
            if variant is not None:
                updates.append("variant_config = ?")
                params.append(json.dumps(variant))
            if traffic_split is not None:
                updates.append("traffic_split = ?")
                params.append(traffic_split)
            if active is not None:
                updates.append("active = ?")
                params.append(1 if active else 0)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(test_id)
            
            query = self._normalize_sql(f"""
                UPDATE ab_tests
                SET {', '.join(updates)}
                WHERE id = ?
            """)
            cursor.execute(query, params)
            conn.commit()
            
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated A/B test {test_id}")
            return updated
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update A/B test: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def deactivate_ab_test(self, test_id: int) -> bool:
        """Deactivate an A/B test."""
        return self.update_ab_test(test_id, active=False)
    
    def assign_ab_variant(
        self,
        conversation_id: int,
        test_id: int,
        get_ab_test_func: callable
    ) -> str:
        """Assign a variant (control or variant) to a conversation for an A/B test."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Check if already assigned
            query = self._normalize_sql("""
                SELECT variant FROM ab_test_assignments
                WHERE test_id = ? AND conversation_id = ?
            """)
            cursor.execute(query, (test_id, conversation_id))
            row = cursor.fetchone()
            
            if row:
                return row[0]
            
            # Get test configuration
            test = get_ab_test_func(test_id)
            if not test:
                raise ValueError(f"A/B test {test_id} not found")
            if not test['active']:
                variant = 'control'
            else:
                # Assign based on traffic split using hash of conversation_id
                hash_val = int(hashlib.md5(f"{test_id}_{conversation_id}".encode()).hexdigest(), 16)
                threshold = test['traffic_split'] * (2**128)
                variant = 'variant' if hash_val < threshold else 'control'
            
            # Store assignment
            query = self._normalize_sql("""
                INSERT INTO ab_test_assignments (test_id, conversation_id, variant)
                VALUES (?, ?, ?)
            """)
            cursor.execute(query, (test_id, conversation_id, variant))
            conn.commit()
            
            logger.debug(f"Assigned variant {variant} to conversation {conversation_id} for test {test_id}")
            return variant
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to assign A/B variant: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def record_ab_metric(
        self,
        test_id: int,
        conversation_id: int,
        variant: str,
        response_time_ms: Optional[int] = None,
        tokens_used: Optional[int] = None,
        user_satisfaction_score: Optional[float] = None,
        error_occurred: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Record metrics for an A/B test response."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                INSERT INTO ab_test_metrics 
                (test_id, conversation_id, variant, response_time_ms, tokens_used, 
                 user_satisfaction_score, error_occurred, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """)
            cursor.execute(query, (
                test_id,
                conversation_id,
                variant,
                response_time_ms,
                tokens_used,
                user_satisfaction_score,
                1 if error_occurred else 0,
                json.dumps(metadata) if metadata else None
            ))
            metric_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            logger.debug(f"Recorded A/B metric {metric_id} for test {test_id}, variant {variant}")
            return metric_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to record A/B metric: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_ab_metrics(self, test_id: int, variant: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get metrics for an A/B test."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            where_clause = "WHERE test_id = ?"
            params = [test_id]
            
            if variant:
                where_clause += " AND variant = ?"
                params.append(variant)
            
            query = self._normalize_sql(f"""
                SELECT id, test_id, conversation_id, variant, response_time_ms, tokens_used,
                       user_satisfaction_score, error_occurred, metadata, recorded_at
                FROM ab_test_metrics
                {where_clause}
                ORDER BY recorded_at DESC
            """)
            cursor.execute(query, params)
            
            metrics = []
            for row in cursor.fetchall():
                metrics.append({
                    'id': row[0],
                    'test_id': row[1],
                    'conversation_id': row[2],
                    'variant': row[3],
                    'response_time_ms': row[4],
                    'tokens_used': row[5],
                    'user_satisfaction_score': row[6],
                    'error_occurred': bool(row[7]),
                    'metadata': json.loads(row[8]) if row[8] else None,
                    'recorded_at': row[9]
                })
            return metrics
        except Exception as e:
            logger.error(f"Failed to get A/B metrics: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_ab_statistics(
        self,
        test_id: int,
        get_ab_metrics_func: callable
    ) -> Dict[str, Any]:
        """Get statistical analysis of A/B test results."""
        conn = self._get_connection()
        try:
            # Get metrics for both variants
            control_metrics = get_ab_metrics_func(test_id, variant='control')
            variant_metrics = get_ab_metrics_func(test_id, variant='variant')
            
            def calculate_stats(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
                if not metrics:
                    return {
                        'count': 0,
                        'avg_response_time_ms': None,
                        'avg_tokens_used': None,
                        'avg_satisfaction_score': None,
                        'error_rate': None
                    }
                
                response_times = [m['response_time_ms'] for m in metrics if m['response_time_ms'] is not None]
                tokens = [m['tokens_used'] for m in metrics if m['tokens_used'] is not None]
                satisfaction_scores = [m['user_satisfaction_score'] for m in metrics if m['user_satisfaction_score'] is not None]
                errors = sum(1 for m in metrics if m['error_occurred'])
                
                return {
                    'count': len(metrics),
                    'avg_response_time_ms': statistics.mean(response_times) if response_times else None,
                    'median_response_time_ms': statistics.median(response_times) if response_times else None,
                    'avg_tokens_used': statistics.mean(tokens) if tokens else None,
                    'avg_satisfaction_score': statistics.mean(satisfaction_scores) if satisfaction_scores else None,
                    'error_rate': errors / len(metrics) if metrics else None
                }
            
            control_stats = calculate_stats(control_metrics)
            variant_stats = calculate_stats(variant_metrics)
            
            return {
                'test_id': test_id,
                'total_samples': len(control_metrics) + len(variant_metrics),
                'control': control_stats,
                'variant': variant_stats
            }
        except Exception as e:
            logger.error(f"Failed to get A/B statistics: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
