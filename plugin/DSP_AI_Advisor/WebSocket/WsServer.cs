using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace DSP_AI_Advisor.WebSocket
{
    /// <summary>
    /// WebSocket Server — 监听端口 8470, 向所有已连接 client 广播快照数据.
    /// 单例模式, 在独立线程上运行 HttpListener.
    /// </summary>
    public class WsServer
    {
        private static readonly Lazy<WsServer> _instance =
            new(() => new WsServer());

        public static WsServer Instance => _instance.Value;

        private readonly object _clientLock = new();
        private readonly List<System.Net.WebSockets.WebSocket> _clients = new();
        private readonly ConcurrentQueue<MessageEnvelope> _incomingQueue = new();
        private HttpListener _listener;
        private CancellationTokenSource _cts;
        private Task _listenTask;

        public const int Port = 8470;
        public bool IsRunning { get; private set; }

        private WsServer() { }

        /// <summary>
        /// 启动 WebSocket 服务器.
        /// </summary>
        public void Start()
        {
            if (IsRunning) return;

            try
            {
                _listener = new HttpListener();
                _listener.Prefixes.Add($"http://localhost:{Port}/");
                _listener.Start();

                _cts = new CancellationTokenSource();
                _listenTask = Task.Run(() => ListenLoop(_cts.Token));

                IsRunning = true;
                Plugin.Log.LogInfo($"[WsServer] Listening on ws://localhost:{Port}/");
            }
            catch (HttpListenerException ex) when (ex.ErrorCode == 5)
            {
                // 权限不足 — Windows 需要 URL ACL
                Plugin.Log.LogWarning(
                    $"[WsServer] Port {Port} requires admin permission. " +
                    $"Run once as admin: netsh http add urlacl url=http://+:{Port}/ user=Everyone");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[WsServer] Failed to start: {ex.Message}");
            }
        }

        /// <summary>
        /// 停止 WebSocket 服务器.
        /// </summary>
        public void Stop()
        {
            if (!IsRunning) return;

            try
            {
                _cts?.Cancel();

                // 关闭所有 client 连接
                List<System.Net.WebSockets.WebSocket> snapshot;
                lock (_clientLock)
                {
                    snapshot = new List<System.Net.WebSockets.WebSocket>(_clients);
                }
                foreach (var client in snapshot)
                {
                    try { client.CloseAsync(WebSocketCloseStatus.NormalClosure, "Server shutting down", CancellationToken.None).Wait(1000); }
                    catch { /* best effort */ }
                }

                _listener?.Stop();
                _listener?.Close();
                IsRunning = false;

                Plugin.Log.LogInfo("[WsServer] Stopped.");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[WsServer] Error during stop: {ex.Message}");
            }
        }

        /// <summary>
        /// 向所有已连接 client 广播文本消息.
        /// </summary>
        public void Broadcast(string message)
        {
            List<System.Net.WebSockets.WebSocket> snapshot;
            lock (_clientLock)
            {
                if (_clients.Count == 0) return;
                snapshot = new List<System.Net.WebSockets.WebSocket>(_clients);
            }

            var buffer = Encoding.UTF8.GetBytes(message);
            var segment = new ArraySegment<byte>(buffer);

            foreach (var client in snapshot)
            {
                if (client.State != WebSocketState.Open) continue;
                try
                {
                    client.SendAsync(segment, WebSocketMessageType.Text, true, CancellationToken.None)
                          .Wait(100);  // 100ms timeout — 不阻塞游戏线程
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[WsServer] Broadcast failed for a client: {ex.Message}");
                }
            }
        }

        /// <summary>
        /// 广播 SnapshotData.
        /// </summary>
        public void BroadcastSnapshot(Models.SnapshotData data)
        {
            var json = MessageCodec.EncodeSnapshot(data);
            Broadcast(json);
        }

        /// <summary>
        /// 广播 GalaxyScanData (全星系扫描结果).
        /// </summary>
        public void BroadcastGalaxyScan(DataCollectors.GalaxyScanData data)
        {
            var json = MessageCodec.EncodeGalaxyScan(data);
            Broadcast(json);
        }

        /// <summary>
        /// 向已连接 Companion 发送命令消息.
        /// </summary>
        public void SendCommand(string type, object payload = null)
        {
            var json = MessageCodec.Encode("command", type, payload ?? new { });
            Broadcast(json);
        }

        /// <summary>
        /// 消费一条入站消息 (非阻塞). UIManager.Update() 中调用.
        /// </summary>
        public bool TryDequeueMessage(out MessageEnvelope envelope)
        {
            return _incomingQueue.TryDequeue(out envelope);
        }

        /// <summary>
        /// 主监听循环 — 接受连接, 升级到 WebSocket, 加入 client 列表.
        /// </summary>
        private async Task ListenLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var context = await _listener.GetContextAsync();
                    if (ct.IsCancellationRequested) break;

                    if (context.Request.IsWebSocketRequest)
                    {
                        // 异步处理 WebSocket 握手 (fire-and-forget)
                        _ = HandleClientAsync(context, ct);
                    }
                    else
                    {
                        context.Response.StatusCode = 400;
                        context.Response.Close();
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (HttpListenerException)
                {
                    break;  // listener stopped
                }
                catch (Exception ex)
                {
                    if (!ct.IsCancellationRequested)
                        Plugin.Log.LogWarning($"[WsServer] Accept error: {ex.Message}");
                }
            }
        }

        private async Task HandleClientAsync(HttpListenerContext context, CancellationToken ct)
        {
            System.Net.WebSockets.WebSocket ws = null;
            try
            {
                var wsContext = await context.AcceptWebSocketAsync(null);
                ws = wsContext.WebSocket;
                lock (_clientLock) { _clients.Add(ws); }

                Plugin.Log.LogInfo($"[WsServer] Client connected. Total: {_clients.Count}");
                MessageRouter.NotifyConnection(true);

                // 保持连接直到 client 断开，同时解析入站消息
                var buffer = new byte[16384];
                var messageBuffer = new StringBuilder();
                while (ws.State == WebSocketState.Open && !ct.IsCancellationRequested)
                {
                    try
                    {
                        var result = await ws.ReceiveAsync(
                            new ArraySegment<byte>(buffer), ct);
                        if (result.MessageType == WebSocketMessageType.Close)
                            break;

                        if (result.MessageType == WebSocketMessageType.Text)
                        {
                            messageBuffer.Append(
                                Encoding.UTF8.GetString(buffer, 0, result.Count));

                            if (result.EndOfMessage)
                            {
                                var raw = messageBuffer.ToString();
                                messageBuffer.Clear();

                                var envelope = MessageCodec.Decode(raw);
                                if (envelope != null)
                                {
                                    _incomingQueue.Enqueue(envelope);
                                }
                            }
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[WsServer] Client handler error: {ex.Message}");
            }
            finally
            {
                if (ws != null)
                {
                    try { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Done", CancellationToken.None); }
                    catch { /* best effort */ }
                }
                // 从 client 列表中移除 — ConcurrentBag 不支持 Remove, 重建
                RemoveClient(ws);
                int remaining;
                lock (_clientLock) { remaining = _clients.Count; }
                Plugin.Log.LogInfo($"[WsServer] Client disconnected. Total: {remaining}");
                if (remaining == 0)
                    MessageRouter.NotifyConnection(false);
            }
        }

        private void RemoveClient(System.Net.WebSockets.WebSocket target)
        {
            lock (_clientLock)
            {
                _clients.Remove(target);
            }
        }
    }
}
