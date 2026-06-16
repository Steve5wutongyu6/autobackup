<template>
  <div>
    <h1 class="view-title">凭据管理</h1>
    <div class="table-toolbar">
      <el-button type="primary" @click="saveCredential">新增凭据</el-button>
    </div>
    <el-card shadow="never">
      <template #header>凭据配置</template>
      <el-alert
        title="Session Token 仅在使用临时密钥时填写；如果你填的是长期 SecretId / SecretKey，请留空。"
        description="当前系统会长期保存凭据用于定时备份。若你填入临时密钥对应的 Session Token，凭据到期后上传会失败，除非你后续手动更新。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-form label-position="top">
        <el-form-item label="凭据名称">
          <el-input v-model="credentialForm.name" />
        </el-form-item>
        <el-form-item label="SecretId">
          <el-input v-model="credentialForm.secret_id" />
        </el-form-item>
        <el-form-item label="SecretKey">
          <el-input v-model="credentialForm.secret_key" show-password type="password" />
        </el-form-item>
        <el-form-item label="Session Token">
          <el-input v-model="credentialForm.session_token" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="credentialForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
    </el-card>
    <el-table :data="credentials" style="margin-top: 24px" border>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="备注" />
      <el-table-column prop="enabled" label="状态">
        <template #default="{ row }">{{ row.enabled ? "启用" : "禁用" }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="180" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="deleteCredential(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { request } from "../api/http";

const credentials = ref([]);
const credentialForm = reactive(createCredentialForm());

/**
 * Build a fresh credential form state.
 *
 * Returns:
 *   Default credential form values.
 */
function createCredentialForm() {
  return {
    name: "",
    secret_id: "",
    secret_key: "",
    session_token: "",
    description: ""
  };
}

/**
 * Reset the credential form after a successful save.
 *
 * Returns:
 *   None. The reactive object is updated in place.
 */
function resetCredentialForm() {
  Object.assign(credentialForm, createCredentialForm());
}

/**
 * Reload credential list from the backend.
 *
 * Returns:
 *   Promise that resolves after the list is refreshed.
 */
async function loadCredentials() {
  credentials.value = await request("/api/cos/credentials");
}

/**
 * Persist a new COS credential.
 *
 * Returns:
 *   Promise that resolves after the credential is saved and the list is refreshed.
 */
async function saveCredential() {
  try {
    await request("/api/cos/credentials", {
      method: "POST",
      body: JSON.stringify(credentialForm)
    });
    ElMessage.success("凭据已保存");
    resetCredentialForm();
    await loadCredentials();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Delete a COS credential when it is no longer referenced by buckets.
 *
 * Args:
 *   credentialId: Credential primary key to delete.
 *
 * Returns:
 *   Promise that resolves after the credential is deleted and the list is refreshed.
 */
async function deleteCredential(credentialId) {
  try {
    await request(`/api/cos/credentials/${credentialId}`, {
      method: "DELETE"
    });
    ElMessage.success("凭据已删除");
    await loadCredentials();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(loadCredentials);
</script>
