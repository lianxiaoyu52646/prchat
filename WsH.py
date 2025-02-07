import json
import asyncio
import aiomysql
from aiohttp import web

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root',
    'db': 'aqchat',
    'charset': 'utf8mb4',
    'autocommit': True
}

# 存储用户连接的字典，键为用户名，值为 WebSocket 连接
connected_users = {}

async def save_message_to_db(pool, sender, content, receiver=None):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            if receiver:
                # 私聊
                await cur.execute("INSERT INTO messages (sender, content, receiver) VALUES (%s, %s, %s)", (sender, content, receiver))
            else:
                # 群聊
                await cur.execute("INSERT INTO messages (sender, content) VALUES (%s, %s)", (sender, content))

async def get_history_messages(pool, username):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 查询与该用户相关的所有消息（包括群聊和私聊）
            query = """
                SELECT sender, content, receiver 
                FROM messages 
                WHERE sender = %s OR receiver = %s OR receiver IS NULL
            """
            await cur.execute(query, (username, username))
            return await cur.fetchall()

async def send_online_users():
    """向所有连接的用户发送在线用户列表"""
    online_users = list(connected_users.keys())
    data = {
        "type": "online_users",
        "users": online_users
    }
    message = json.dumps(data)
    for user, ws in connected_users.items():
        try:
            await ws.send_str(message)
        except Exception as e:
            print(f"发送在线用户列表给 {user} 时出错: {e}")

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    print("客户端已连接")

    pool = request.app['db_pool']
    username = None

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get('type')

                    if msg_type == 'login':
                        username = data.get('username')
                        if username:
                            # 检查用户是否已经在连接列表中，如果是刷新页面，不进行重复添加和广播加入消息
                            if username not in connected_users:
                                connected_users[username] = ws
                                print(f"{username} 已登录")
                                # 广播用户加入消息
                                join_data = {
                                    "type": "user_join",
                                    "username": username
                                }
                                join_message = json.dumps(join_data)
                                for user, user_ws in connected_users.items():
                                    if user != username:
                                        try:
                                            await user_ws.send_str(join_message)
                                        except Exception as e:
                                            print(f"发送用户加入消息给 {user} 时出错: {e}")
                            else:
                                # 刷新页面，更新连接
                                connected_users[username] = ws
                            # 向新登录/刷新的用户发送在线用户列表
                            await send_online_users()
                            # 获取历史消息并发送给用户
                            history_messages = await get_history_messages(pool, username)
                            for msg in history_messages:
                                msg_data = {
                                    "type": "message",
                                    "sender": msg['sender'],
                                    "content": msg['content'],
                                    "receiver": msg['receiver']
                                }
                                await ws.send_str(json.dumps(msg_data))

                    elif msg_type == 'message':
                        sender = data.get('sender')
                        content = data.get('content')
                        receiver = data.get('receiver')

                        if sender and content:
                            print(f"收到消息: {msg.data}")
                            # 保存消息到数据库
                            await save_message_to_db(pool, sender, content, receiver)

                            if receiver:
                                # 私聊消息
                                if receiver in connected_users:
                                    await connected_users[receiver].send_str(json.dumps(data))
                                    # 自己发送的私聊消息也显示
                                    await ws.send_str(json.dumps(data))
                            else:
                                # 群聊消息
                                for user, user_ws in connected_users.items():
                                    await user_ws.send_str(json.dumps(data))

                except json.JSONDecodeError as e:
                    print(f"JSON 解析错误: {e}")
            elif msg.type == web.WSMsgType.ERROR:
                print(f"WebSocket 错误: {ws.exception()}")
    finally:
        if username and username in connected_users:
            try:
                # 尝试关闭连接
                await ws.close()
            except Exception as e:
                print(f"关闭 {username} 的 WebSocket 连接时出错: {e}")
            # 仅当连接确实关闭时才移除用户
            if ws.closed:
                del connected_users[username]
                print(f"{username} 已断开连接")
                # 广播用户离开消息
                leave_data = {
                    "type": "user_leave",
                    "username": username
                }
                leave_message = json.dumps(leave_data)
                for user, user_ws in connected_users.items():
                    try:
                        await user_ws.send_str(leave_message)
                    except Exception as e:
                        print(f"发送用户离开消息给 {user} 时出错: {e}")
                # 发送更新后的在线用户列表
                await send_online_users()

    return ws

async def init_db(app):
    pool = await aiomysql.create_pool(**DB_CONFIG)
    app['db_pool'] = pool

async def close_db(app):
    app['db_pool'].close()
    await app['db_pool'].wait_closed()

app = web.Application()
app.router.add_get("/ws/websocket", websocket_handler)

app.on_startup.append(init_db)
app.on_cleanup.append(close_db)

if __name__ == "__main__":
    web.run_app(app, port=8025)