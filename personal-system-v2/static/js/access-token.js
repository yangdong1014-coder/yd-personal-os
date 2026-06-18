const ACCESS_TOKEN_STORAGE_KEY = "personal_os_access_token";

function initAccessTokenFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = (params.get("token") || "").trim();
  if (!token) return;
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
}

function getStoredAccessToken() {
  return (localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) || "").trim();
}

function getAccessTokenHeaders() {
  const token = getStoredAccessToken();
  if (!token) return {};
  return { "X-Personal-OS-Token": token };
}

initAccessTokenFromUrl();