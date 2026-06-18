async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const raw = await response.text();
  let payload;
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch (_error) {
    if (raw.trim().toLowerCase().startsWith("<!doctype") || raw.trim().startsWith("<html")) {
      throw new Error(
        `服务器返回了错误页面（HTTP ${response.status}），请查看终端日志或重启服务后重试`
      );
    }
    throw new Error(`服务器响应格式异常（HTTP ${response.status}）`);
  }
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `请求失败（HTTP ${response.status}）`);
  }
  return payload.data;
}