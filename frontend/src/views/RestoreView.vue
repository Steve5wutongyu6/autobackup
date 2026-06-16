<template>
  <div>
    <h1 class="view-title">恢复作业中心</h1>
    <el-table :data="restoreJobs" border>
      <el-table-column prop="artifact_id" label="备份 ID" />
      <el-table-column prop="restore_path" label="恢复路径" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="checksum_verified" label="校验通过">
        <template #default="{ row }">{{ row.checksum_verified ? "是" : "否" }}</template>
      </el-table-column>
      <el-table-column prop="error_message" label="错误信息" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button
            v-if="row.requires_public_confirm"
            type="warning"
            size="small"
            @click="confirmPublic(row.id)"
          >
            确认公网下载
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { request } from "../api/http";

const restoreJobs = ref([]);

/**
 * Load restore job history from the backend.
 *
 * Returns:
 *   Promise that resolves after the restore job list is loaded.
 */
async function loadRestoreJobs() {
  restoreJobs.value = await request("/api/restore-jobs");
}

/**
 * Approve a restore job to continue with public COS egress.
 *
 * Args:
 *   restoreJobId: Restore job primary key.
 *
 * Returns:
 *   Promise that resolves after the backend records approval.
 */
async function confirmPublic(restoreJobId) {
  try {
    await request(`/api/restore-jobs/${restoreJobId}/confirm-public-download`, {
      method: "POST"
    });
    ElMessage.success("已确认公网下载");
    await loadRestoreJobs();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(loadRestoreJobs);
</script>
