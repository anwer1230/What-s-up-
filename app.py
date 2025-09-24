#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import logging
from flask import Flask, session, request, render_template_string, jsonify, redirect
from flask_socketio import SocketIO

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", os.urandom(24))

# إعداد SocketIO لـ Render
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)

# نظام المستخدمين
PREDEFINED_USERS = {
    "user_1": {"id": "user_1", "name": "المستخدم الأول", "icon": "fas fa-user", "color": "#007bff"},
    "user_2": {"id": "user_2", "name": "المستخدم الثاني", "icon": "fas fa-user-tie", "color": "#28a745"},
    "user_3": {"id": "user_3", "name": "المستخدم الثالث", "icon": "fas fa-user-graduate", "color": "#ffc107"},
    "user_4": {"id": "user_4", "name": "المستخدم الرابع", "icon": "fas fa-user-cog", "color": "#dc3545"},
    "user_5": {"id": "user_5", "name": "المستخدم الخامس", "icon": "fas fa-user-astronaut", "color": "#6f42c1"}
}

def load_html_template():
    """تحميل قالب HTML من الملف في المجلد الرئيسي"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error("index.html not found in root directory")
        return "<h1>Error: index.html not found</h1>"

@app.route('/')
def index():
    user_id = request.args.get('user_id', 'user_1')
    session['user_id'] = user_id
    
    # التأكد من وجود المجلدات
    os.makedirs('sessions', exist_ok=True)
    
    # تحميل HTML من الملف الرئيسي
    html_content = load_html_template()
    
    return render_template_string(html_content,
                         settings={},
                         connection_status='disconnected',
                         app_title="مركز سرعة انجاز 📚للخدمات الطلابية والاكاديمية",
                         predefined_users=PREDEFINED_USERS)

@app.route('/health')
def health_check():
    """نقطة فحص الصحة لـ Render"""
    return jsonify({"status": "healthy", "message": "WhatsApp Monitor is running"})

@socketio.on('connect')
def handle_connect():
    user_id = session.get('user_id', 'user_1')
    logger.info(f"Client connected: {user_id}")
    socketio.emit('log_update', {
        "message": "🔗 تم الاتصال بالخادم بنجاح"
    }, room=request.sid)

@socketio.on('start_whatsapp_connection')
def handle_start_connection(data):
    user_id = session.get('user_id', 'user_1')
    try:
        from whatsapp_manager import whatsapp_manager
        result = whatsapp_manager.start_connection(user_id)
        
        if result['status'] == 'qr_code':
            socketio.emit('qr_code_received', {
                'qr_code': result['qr_code'],
                'message': result['message']
            }, room=request.sid)
        else:
            socketio.emit('connection_error', {
                'message': result['message']
            }, room=request.sid)
    except Exception as e:
        logger.error(f"Connection error: {e}")
        socketio.emit('connection_error', {
            'message': f"خطأ في الخادم: {str(e)}"
        }, room=request.sid)

@socketio.on('send_whatsapp_message')
def handle_send_message(data):
    user_id = session.get('user_id', 'user_1')
    try:
        from whatsapp_manager import whatsapp_manager
        result = whatsapp_manager.send_message(user_id, data['phone_number'], data['message'])
        socketio.emit('message_sent', result, room=request.sid)
    except Exception as e:
        logger.error(f"Send message error: {e}")
        socketio.emit('message_sent', {
            'status': 'error',
            'message': f"خطأ في الإرسال: {str(e)}"
        }, room=request.sid)

@socketio.on('update_monitoring_keywords')
def handle_update_keywords(data):
    user_id = session.get('user_id', 'user_1')
    try:
        from whatsapp_manager import whatsapp_manager
        result = whatsapp_manager.update_monitoring(user_id, data['keywords'])
        socketio.emit('monitoring_updated', result, room=request.sid)
    except Exception as e:
        logger.error(f"Update keywords error: {e}")
        socketio.emit('monitoring_updated', {
            'status': 'error',
            'message': f"خطأ في التحديث: {str(e)}"
        }, room=request.sid)

@socketio.on('disconnect_whatsapp')
def handle_disconnect():
    user_id = session.get('user_id', 'user_1')
    try:
        from whatsapp_manager import whatsapp_manager
        result = whatsapp_manager.disconnect(user_id)
        socketio.emit('connection_status', {
            'status': 'disconnected',
            'authenticated': False
        }, room=request.sid)
    except Exception as e:
        logger.error(f"Disconnect error: {e}")

def initialize_system():
    """تهيئة النظام"""
    try:
        logger.info("🚀 Starting WhatsApp Monitoring System on Render...")
        
        # التأكد من وجود المجلدات
        os.makedirs('sessions', exist_ok=True)
        
        # تحميل الجلسات
        from whatsapp_manager import load_all_sessions, alert_queue
        sessions_loaded = load_all_sessions()
        logger.info(f"📂 Loaded {sessions_loaded} sessions")
        
        # بدء نظام التنبيهات
        alert_queue.start()
        logger.info("✅ System initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ System initialization failed: {e}")

if __name__ == '__main__':
    initialize_system()
    
    # الحصول على PORT من environment variable (مطلوب لـ Render)
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"🌐 Starting server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
