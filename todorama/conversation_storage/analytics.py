"""Conversation analytics operations."""

import json
import csv
import io
import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import dateutil for flexible date parsing
try:
    from dateutil.parser import parse as parse_date
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False
    def parse_date(date_str):
        """Fallback date parser using datetime.fromisoformat."""
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except:
                return None


class ConversationAnalytics:
    """Manages conversation analytics and reporting."""
    
    def __init__(self, adapter, normalize_sql_func):
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        return self.adapter.connect()
    
    def get_conversation_analytics(
        self,
        user_id: str,
        chat_id: str,
        get_conversation_func: callable = None
    ) -> Dict[str, Any]:
        """Get analytics metrics for a specific conversation."""
        if get_conversation_func:
            conversation = get_conversation_func(user_id, chat_id)
        else:
            return {}
        
        if not conversation:
            return {}
        
        messages = conversation.get('messages', [])
        if not messages:
            return {
                'message_count': 0,
                'total_tokens': 0,
                'average_response_time_seconds': 0,
                'user_engagement_score': 0,
                'conversation_duration_seconds': 0
            }
        
        # Calculate response times
        response_times = []
        user_messages = []
        
        for i, msg in enumerate(messages):
            if msg['role'] == 'user':
                user_messages.append((i, msg.get('created_at')))
            elif msg['role'] == 'assistant' and user_messages:
                user_idx, user_time = user_messages[-1]
                if user_idx < i:
                    assistant_time = msg.get('created_at')
                    if user_time and assistant_time:
                        try:
                            if isinstance(user_time, str):
                                user_time = parse_date(user_time)
                            if isinstance(assistant_time, str):
                                assistant_time = parse_date(assistant_time)
                            
                            if isinstance(user_time, datetime):
                                if isinstance(assistant_time, datetime):
                                    delta = (assistant_time - user_time).total_seconds()
                                    if delta > 0:
                                        response_times.append(delta)
                        except Exception as e:
                            logger.debug(f"Could not calculate response time: {e}")
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Calculate engagement score
        user_msg_count = sum(1 for msg in messages if msg['role'] == 'user')
        engagement_score = min(100, user_msg_count * 10 + (1.0 / (avg_response_time + 1)) * 10) if avg_response_time > 0 else user_msg_count * 10
        
        # Calculate conversation duration
        first_msg_time = messages[0].get('created_at') if messages else None
        last_msg_time = messages[-1].get('created_at') if messages else None
        duration = 0
        if first_msg_time and last_msg_time:
            try:
                if isinstance(first_msg_time, str):
                    first_msg_time = parse_date(first_msg_time)
                if isinstance(last_msg_time, str):
                    last_msg_time = parse_date(last_msg_time)
                
                if isinstance(first_msg_time, datetime) and isinstance(last_msg_time, datetime):
                    duration = (last_msg_time - first_msg_time).total_seconds()
            except Exception as e:
                logger.debug(f"Could not calculate duration: {e}")
        
        return {
            'message_count': conversation.get('message_count', len(messages)),
            'total_tokens': conversation.get('total_tokens', 0),
            'average_response_time_seconds': round(avg_response_time, 2),
            'user_engagement_score': round(engagement_score, 2),
            'conversation_duration_seconds': round(duration, 2),
            'response_times': [round(rt, 2) for rt in response_times],
            'user_message_count': user_msg_count,
            'assistant_message_count': sum(1 for msg in messages if msg['role'] == 'assistant')
        }
    
    def get_dashboard_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        list_conversations_func: callable = None,
        get_conversation_analytics_func: callable = None
    ) -> Dict[str, Any]:
        """Get dashboard analytics aggregating data across conversations."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Build WHERE clause
            where_clauses = []
            params = []
            
            if user_id:
                where_clauses.append("c.user_id = ?")
                params.append(user_id)
            
            if start_date:
                where_clauses.append("c.created_at >= ?")
                params.append(start_date)
            if end_date:
                where_clauses.append("c.created_at <= ?")
                params.append(end_date)
            
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            # Get total conversations
            query = self._normalize_sql(f"""
                SELECT COUNT(*) FROM conversations c
                {where_sql}
            """)
            cursor.execute(query, tuple(params))
            total_conversations = cursor.fetchone()[0] or 0
            
            # Get active users
            query = self._normalize_sql(f"""
                SELECT COUNT(DISTINCT user_id) FROM conversations c
                {where_sql}
            """)
            cursor.execute(query, tuple(params))
            active_users = cursor.fetchone()[0] or 0
            
            # Get total messages
            query = self._normalize_sql(f"""
                SELECT COALESCE(SUM(c.message_count), 0) FROM conversations c
                {where_sql}
            """)
            cursor.execute(query, tuple(params))
            total_messages = cursor.fetchone()[0] or 0
            
            # Calculate average response times across conversations
            if list_conversations_func and get_conversation_analytics_func:
                conversations = list_conversations_func(user_id=user_id, limit=1000)
                response_times = []
                engagement_scores = []
                
                for conv in conversations:
                    if start_date and conv.get('created_at'):
                        try:
                            conv_date = conv['created_at']
                            if isinstance(conv_date, str):
                                conv_date = parse_date(conv_date)
                            if isinstance(conv_date, datetime) and conv_date < start_date:
                                continue
                        except:
                            pass
                    if end_date and conv.get('created_at'):
                        try:
                            conv_date = conv['created_at']
                            if isinstance(conv_date, str):
                                conv_date = parse_date(conv_date)
                            if isinstance(conv_date, datetime) and conv_date > end_date:
                                continue
                        except:
                            pass
                    
                    analytics = get_conversation_analytics_func(conv['user_id'], conv['chat_id'])
                    if analytics.get('average_response_time_seconds', 0) > 0:
                        response_times.append(analytics['average_response_time_seconds'])
                    if analytics.get('user_engagement_score', 0) > 0:
                        engagement_scores.append(analytics['user_engagement_score'])
                
                avg_response_time = sum(response_times) / len(response_times) if response_times else 0
                avg_engagement = sum(engagement_scores) / len(engagement_scores) if engagement_scores else 0
            else:
                avg_response_time = 0
                avg_engagement = 0
                engagement_scores = []
            
            return {
                'total_conversations': total_conversations,
                'active_users': active_users,
                'total_messages': total_messages,
                'average_response_time': round(avg_response_time, 2),
                'engagement_metrics': {
                    'average_engagement_score': round(avg_engagement, 2),
                    'high_engagement_conversations': sum(1 for s in engagement_scores if s > 70),
                    'medium_engagement_conversations': sum(1 for s in engagement_scores if 40 <= s <= 70),
                    'low_engagement_conversations': sum(1 for s in engagement_scores if s < 40)
                },
                'date_range': {
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None
                } if start_date or end_date else None
            }
        finally:
            self.adapter.close(conn)
    
    def generate_analytics_report(
        self,
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        get_dashboard_analytics_func: callable = None,
        list_conversations_func: callable = None,
        get_conversation_analytics_func: callable = None
    ) -> Union[Dict[str, Any], str]:
        """Generate analytics report in specified format."""
        if get_dashboard_analytics_func:
            dashboard = get_dashboard_analytics_func(start_date, end_date, user_id)
        else:
            dashboard = self.get_dashboard_analytics(start_date, end_date, user_id)
        
        if list_conversations_func:
            conversations = list_conversations_func(user_id=user_id, limit=1000)
        else:
            conversations = []
        
        # Filter conversations by date if needed
        filtered_conversations = []
        for conv in conversations:
            include = True
            if start_date and conv.get('created_at'):
                try:
                    conv_date = conv['created_at']
                    if isinstance(conv_date, str):
                        conv_date = parse_date(conv_date)
                    if isinstance(conv_date, datetime) and conv_date < start_date:
                        include = False
                except:
                    pass
            if end_date and conv.get('created_at'):
                try:
                    conv_date = conv['created_at']
                    if isinstance(conv_date, str):
                        conv_date = parse_date(conv_date)
                    if isinstance(conv_date, datetime) and conv_date > end_date:
                        include = False
                except:
                    pass
            if include:
                filtered_conversations.append(conv)
        
        # Get detailed analytics for each conversation
        conversation_details = []
        for conv in filtered_conversations:
            if get_conversation_analytics_func:
                analytics = get_conversation_analytics_func(conv['user_id'], conv['chat_id'])
            else:
                analytics = self.get_conversation_analytics(conv['user_id'], conv['chat_id'])
            conversation_details.append({
                'user_id': conv['user_id'],
                'chat_id': conv['chat_id'],
                'created_at': conv['created_at'].isoformat() if isinstance(conv.get('created_at'), datetime) else str(conv.get('created_at', '')),
                'message_count': analytics.get('message_count', 0),
                'total_tokens': analytics.get('total_tokens', 0),
                'average_response_time_seconds': analytics.get('average_response_time_seconds', 0),
                'user_engagement_score': analytics.get('user_engagement_score', 0)
            })
        
        if format == "json":
            return {
                'report_generated_at': datetime.now().isoformat(),
                'dashboard_summary': dashboard,
                'conversations': conversation_details,
                'filters': {
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None,
                    'user_id': user_id
                }
            }
        elif format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'User ID', 'Chat ID', 'Created At', 'Message Count',
                'Total Tokens', 'Avg Response Time (s)', 'Engagement Score'
            ])
            
            # Write data
            for conv in conversation_details:
                writer.writerow([
                    conv['user_id'],
                    conv['chat_id'],
                    conv['created_at'],
                    conv['message_count'],
                    conv['total_tokens'],
                    conv['average_response_time_seconds'],
                    conv['user_engagement_score']
                ])
            
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported report format: {format}. Supported: json, csv")
