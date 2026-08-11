const adminUsersList = document.getElementById("admin-users-list");
const createUserForm = document.getElementById("admin-create-user-form");
const adminUsersStatus = document.getElementById("admin-users-status");
const temporaryPasswordPanel = document.getElementById("temporary-password-panel");
const temporaryPasswordValue = document.getElementById("temporary-password-value");
const temporaryPasswordOwner = document.getElementById("temporary-password-owner");
const copyTemporaryPasswordButton = document.getElementById("copy-temporary-password");

let adminUsers = Array.isArray(window.INITIAL_ADMIN_USERS)
  ? window.INITIAL_ADMIN_USERS
  : [];

function setAdminStatus(message, isError = false) {
  adminUsersStatus.textContent = message || "";
  adminUsersStatus.classList.toggle("is-error", isError);
}

function showTemporaryPassword(username, password) {
  temporaryPasswordValue.textContent = password;
  temporaryPasswordOwner.textContent = `账户：${username}。关闭或刷新页面后无法再次查看。`;
  temporaryPasswordPanel.hidden = false;
}

function createUserMeta(user) {
  const meta = document.createElement("div");
  meta.className = "admin-user-meta";

  const identity = document.createElement("div");
  identity.className = "admin-user-identity";
  const name = document.createElement("strong");
  name.textContent = user.username;
  const email = document.createElement("span");
  email.textContent = user.email;
  identity.append(name, email);

  const badges = document.createElement("div");
  badges.className = "admin-user-badges";
  const role = document.createElement("span");
  role.className = "tag";
  role.textContent = user.role === "admin" ? "管理员" : "普通用户";
  const status = document.createElement("span");
  status.className = `tag ${user.is_active ? "admin-user-active" : "admin-user-disabled"}`;
  status.textContent = user.is_active ? "已启用" : "已禁用";
  badges.append(role, status);
  if (user.must_change_password) {
    const pending = document.createElement("span");
    pending.className = "tag admin-user-password-pending";
    pending.textContent = "待改密码";
    badges.append(pending);
  }

  meta.append(identity, badges);
  return meta;
}

function createActionButton(label, className, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `btn btn-sm ${className}`.trim();
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

async function toggleUser(user) {
  const nextActive = !user.is_active;
  const action = nextActive ? "启用" : "禁用";
  if (!window.confirm(`确认${action}用户「${user.username}」？`)) return;
  setAdminStatus(`${action}中…`);
  try {
    const updated = await apiRequest(`/api/admin/users/${user.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: nextActive }),
    });
    adminUsers = adminUsers.map((item) => (item.id === updated.id ? updated : item));
    renderAdminUsers();
    setAdminStatus(`已${action} ${updated.username}`);
  } catch (error) {
    setAdminStatus(error.message, true);
  }
}

async function resetUserPassword(user) {
  if (!window.confirm(`确认重置用户「${user.username}」的密码？其旧登录状态会立即失效。`)) return;
  setAdminStatus("正在重置密码…");
  try {
    const result = await apiRequest(`/api/admin/users/${user.id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    adminUsers = adminUsers.map((item) =>
      item.id === result.user.id ? result.user : item
    );
    renderAdminUsers();
    showTemporaryPassword(result.user.username, result.temporary_password);
    setAdminStatus(`已重置 ${result.user.username} 的密码`);
  } catch (error) {
    setAdminStatus(error.message, true);
  }
}

function renderAdminUsers() {
  adminUsersList.replaceChildren();
  adminUsers.forEach((user) => {
    const row = document.createElement("article");
    row.className = "admin-user-row";
    row.append(createUserMeta(user));

    const actions = document.createElement("div");
    actions.className = "admin-user-actions";
    if (user.role === "user") {
      actions.append(
        createActionButton(
          user.is_active ? "禁用" : "启用",
          "btn-ghost",
          () => toggleUser(user)
        ),
        createActionButton("重置密码", "btn-ghost", () => resetUserPassword(user))
      );
    } else {
      const note = document.createElement("span");
      note.className = "form-hint";
      note.textContent = "bootstrap 管理员";
      actions.append(note);
    }
    row.append(actions);
    adminUsersList.append(row);
  });
}

createUserForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = createUserForm.querySelector('button[type="submit"]');
  const formData = new FormData(createUserForm);
  submitButton.disabled = true;
  setAdminStatus("正在创建用户…");
  temporaryPasswordPanel.hidden = true;
  try {
    const result = await apiRequest("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username: formData.get("username"),
        email: formData.get("email"),
      }),
    });
    adminUsers.push(result.user);
    adminUsers.sort((left, right) => left.username.localeCompare(right.username));
    renderAdminUsers();
    createUserForm.reset();
    showTemporaryPassword(result.user.username, result.temporary_password);
    setAdminStatus(`已创建 ${result.user.username}`);
  } catch (error) {
    setAdminStatus(error.message, true);
  } finally {
    submitButton.disabled = false;
  }
});

copyTemporaryPasswordButton.addEventListener("click", async () => {
  const password = temporaryPasswordValue.textContent;
  if (!password) return;
  try {
    await navigator.clipboard.writeText(password);
    setAdminStatus("临时密码已复制");
  } catch (_error) {
    setAdminStatus("浏览器未允许自动复制，请手动复制", true);
  }
});

renderAdminUsers();
