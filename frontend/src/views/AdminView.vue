<template>
  <div>
    <h1 class="view-title">管理员中心</h1>
    <el-row :gutter="24">
      <el-col :md="12" :span="24">
        <el-card shadow="never">
          <template #header>管理员资料</template>
          <el-form label-position="top">
            <el-form-item label="用户名">
              <el-input v-model="profile.username" />
            </el-form-item>
            <el-button type="primary" @click="saveUsername">保存用户名</el-button>
          </el-form>
        </el-card>
      </el-col>
      <el-col :md="12" :span="24">
        <el-card shadow="never">
          <template #header>修改密码</template>
          <el-form label-position="top">
            <el-form-item label="当前密码">
              <el-input v-model="passwordForm.current_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="passwordForm.new_password" type="password" show-password />
            </el-form-item>
            <el-button type="success" @click="savePassword">更新密码</el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 24px">
      <template #header>Passkey</template>
      <div style="display: flex; gap: 12px; margin-bottom: 16px; align-items: center">
        <el-input v-model="passkeyName" placeholder="新的 Passkey 名称" style="max-width: 320px" />
        <el-button type="primary" @click="registerPasskey">新增 Passkey</el-button>
      </div>
      <el-table :data="passkeys" border>
        <el-table-column prop="friendly_name" label="名称" />
        <el-table-column prop="credential_id" label="Credential ID" />
        <el-table-column prop="last_used_at" label="最近使用" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="danger" size="small" @click="deletePasskey(row.credential_id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { request } from "../api/http";
import { normalizeRegistrationOptions, serializeRegistrationCredential } from "../utils/webauthn";

const profile = reactive({
  username: ""
});
const passwordForm = reactive({
  current_password: "",
  new_password: ""
});
const passkeys = ref([]);
const passkeyName = ref("New Passkey");

/**
 * Load admin profile and passkey data.
 *
 * Returns:
 *   Promise that resolves after the administrator view data is refreshed.
 */
async function loadAdmin() {
  const [profileData, passkeyData] = await Promise.all([
    request("/api/admin/profile"),
    request("/api/admin/passkeys")
  ]);
  profile.username = profileData.username;
  passkeys.value = passkeyData;
}

/**
 * Persist a new administrator username.
 *
 * Returns:
 *   Promise that resolves after the username is updated.
 */
async function saveUsername() {
  try {
    await request("/api/admin/profile", {
      method: "PUT",
      body: JSON.stringify({ username: profile.username })
    });
    ElMessage.success("用户名已更新");
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Persist a new administrator password.
 *
 * Returns:
 *   Promise that resolves after the password is updated.
 */
async function savePassword() {
  try {
    await request("/api/admin/password", {
      method: "POST",
      body: JSON.stringify(passwordForm)
    });
    ElMessage.success("密码已更新");
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Delete a stored passkey by credential ID.
 *
 * Args:
 *   credentialId: WebAuthn credential identifier.
 *
 * Returns:
 *   Promise that resolves after the passkey is deleted.
 */
async function deletePasskey(credentialId) {
  try {
    await request(`/api/admin/passkeys/${credentialId}`, {
      method: "DELETE"
    });
    ElMessage.success("Passkey 已删除");
    await loadAdmin();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Register a new Passkey from the administrator center.
 *
 * Returns:
 *   Promise that resolves after the backend stores the verified Passkey.
 */
async function registerPasskey() {
  try {
    const optionsResponse = await request("/api/admin/passkeys/register/options", {
      method: "POST",
      body: JSON.stringify({ friendly_name: passkeyName.value })
    });
    const credential = await navigator.credentials.create({
      publicKey: normalizeRegistrationOptions(optionsResponse.public_key)
    });
    await request("/api/admin/passkeys/register/verify", {
      method: "POST",
      body: JSON.stringify({
        challenge_token: optionsResponse.challenge_token,
        credential: serializeRegistrationCredential(credential)
      })
    });
    ElMessage.success("Passkey 已注册");
    await loadAdmin();
  } catch (error) {
    ElMessage.error(error.message || "Passkey 注册失败");
  }
}

onMounted(loadAdmin);
</script>
