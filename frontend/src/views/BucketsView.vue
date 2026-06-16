<template>
  <div>
    <h1 class="view-title">存储桶管理</h1>
    <div class="table-toolbar">
      <el-button type="success" @click="saveBucket">新增存储桶</el-button>
    </div>
    <el-alert
      v-if="credentials.length === 0"
      title="当前还没有可用凭据，请先前往“凭据管理”创建 COS 凭据。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />
    <el-card shadow="never">
      <template #header>存储桶配置</template>
      <el-form label-position="top">
        <el-form-item label="使用凭据">
          <el-select v-model="bucketForm.credential_id" style="width: 100%">
            <el-option
              v-for="credential in credentials"
              :key="credential.id"
              :label="credential.name"
              :value="credential.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Bucket Name">
          <el-input v-model="bucketForm.name" />
        </el-form-item>
        <el-form-item label="AppID">
          <el-input v-model="bucketForm.app_id" />
        </el-form-item>
        <el-form-item label="Region">
          <el-input v-model="bucketForm.region" placeholder="例如 ap-guangzhou" />
        </el-form-item>
        <el-form-item label="Endpoint Mode">
          <el-select v-model="bucketForm.endpoint_mode" style="width: 100%">
            <el-option label="默认 COS" value="default" />
            <el-option label="全球加速" value="accelerate" />
            <el-option label="自定义域名" value="custom" />
            <el-option label="CDN 域名" value="cdn" />
          </el-select>
        </el-form-item>
        <el-form-item label="自定义 Endpoint">
          <el-input v-model="bucketForm.custom_endpoint" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="bucketForm.user_expected_private_route">期望同地域内网访问</el-checkbox>
        </el-form-item>
      </el-form>
    </el-card>
    <el-table :data="buckets" style="margin-top: 24px" border>
      <el-table-column prop="name" label="Bucket" />
      <el-table-column prop="region" label="地域" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="last_nslookup_ip" label="最近解析 IP" />
      <el-table-column prop="last_nslookup_private" label="私网">
        <template #default="{ row }">{{ row.last_nslookup_private ? "是" : "否" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="checkBucket(row.id)">检测连通性</el-button>
          <el-button size="small" type="danger" @click="deleteBucket(row.id)">删除</el-button>
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
const buckets = ref([]);
const bucketForm = reactive(createBucketForm());

/**
 * Build a fresh bucket form state.
 *
 * Returns:
 *   Default bucket form values.
 */
function createBucketForm() {
  return {
    credential_id: null,
    name: "",
    app_id: "",
    region: "",
    endpoint_mode: "default",
    custom_endpoint: "",
    use_https: true,
    user_expected_private_route: false
  };
}

/**
 * Reset the bucket form after a successful save.
 *
 * Returns:
 *   None. The reactive object is updated in place.
 */
function resetBucketForm() {
  Object.assign(bucketForm, createBucketForm());
}

/**
 * Reload bucket and credential lists from the backend.
 *
 * Returns:
 *   Promise that resolves after both lists are refreshed.
 */
async function loadData() {
  [credentials.value, buckets.value] = await Promise.all([request("/api/cos/credentials"), request("/api/cos/buckets")]);
}

/**
 * Persist a new bucket definition.
 *
 * Returns:
 *   Promise that resolves after the bucket is saved and the list is refreshed.
 */
async function saveBucket() {
  try {
    await request("/api/cos/buckets", {
      method: "POST",
      body: JSON.stringify(bucketForm)
    });
    ElMessage.success("存储桶已保存");
    resetBucketForm();
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Run a private-route and connectivity check for the chosen bucket.
 *
 * Args:
 *   bucketId: Bucket primary key to validate.
 *
 * Returns:
 *   Promise that resolves after the bucket check completes.
 */
async function checkBucket(bucketId) {
  try {
    const result = await request(`/api/cos/buckets/${bucketId}/check`, {
      method: "POST"
    });
    ElMessage.success(`${result.status}: ${result.detail}`);
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Delete a bucket definition from the backend.
 *
 * Args:
 *   bucketId: Bucket primary key to delete.
 *
 * Returns:
 *   Promise that resolves after the bucket is deleted and the list is refreshed.
 */
async function deleteBucket(bucketId) {
  try {
    await request(`/api/cos/buckets/${bucketId}`, {
      method: "DELETE"
    });
    ElMessage.success("存储桶已删除");
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(loadData);
</script>
