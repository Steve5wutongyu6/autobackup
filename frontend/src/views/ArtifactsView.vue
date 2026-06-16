<template>
  <div>
    <h1 class="view-title">备份文件</h1>
    <el-table :data="artifacts" border>
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-table :data="row.replicas" border>
            <el-table-column prop="bucket_id" label="桶 ID" />
            <el-table-column prop="object_key" label="对象 Key" />
            <el-table-column prop="upload_status" label="上传状态" />
            <el-table-column prop="is_private_route_verified" label="最近私网检测">
              <template #default="{ row: replica }">{{ replica.is_private_route_verified ? "是" : "否" }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误信息" />
          </el-table>
        </template>
      </el-table-column>
      <el-table-column prop="archive_name" label="文件名" />
      <el-table-column prop="source_path" label="原目录" />
      <el-table-column prop="size_bytes" label="大小" />
      <el-table-column prop="status" label="状态" />
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button size="small" @click="openRestoreDialog(row)">恢复</el-button>
          <el-button size="small" type="danger" @click="deleteArtifact(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="restoreDialogVisible" title="创建恢复作业" width="520px">
      <el-form label-position="top">
        <el-form-item label="恢复目标路径">
          <el-input v-model="restorePath" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="restoreDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createRestoreJob">开始恢复</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { request } from "../api/http";

const artifacts = ref([]);
const restoreDialogVisible = ref(false);
const selectedArtifact = ref(null);
const restorePath = ref("");

/**
 * Load logical backup artifacts and their replica summaries.
 *
 * Returns:
 *   Promise that resolves after the artifact list is fetched.
 */
async function loadArtifacts() {
  artifacts.value = await request("/api/artifacts");
}

/**
 * Open the restore dialog and prefill the original source path.
 *
 * Args:
 *   artifact: Selected logical artifact row.
 *
 * Returns:
 *   None. Dialog state is updated.
 */
function openRestoreDialog(artifact) {
  selectedArtifact.value = artifact;
  restorePath.value = artifact.source_path;
  restoreDialogVisible.value = true;
}

/**
 * Create a restore job for the chosen artifact.
 *
 * Returns:
 *   Promise that resolves after the restore job is created.
 */
async function createRestoreJob() {
  try {
    const job = await request(`/api/artifacts/${selectedArtifact.value.id}/restore`, {
      method: "POST",
      body: JSON.stringify({ restore_path: restorePath.value })
    });
    restoreDialogVisible.value = false;
    if (job.requires_public_confirm) {
      ElMessage.warning("未找到可用内网副本，恢复已暂停，需到恢复作业页确认公网下载。");
    } else {
      ElMessage.success("恢复作业已创建");
    }
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Delete a logical artifact and all of its bucket replicas.
 *
 * Args:
 *   artifactId: Artifact primary key.
 *
 * Returns:
 *   Promise that resolves after the artifact is deleted and the list is refreshed.
 */
async function deleteArtifact(artifactId) {
  try {
    await request(`/api/artifacts/${artifactId}`, {
      method: "DELETE"
    });
    ElMessage.success("备份已删除");
    await loadArtifacts();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(loadArtifacts);
</script>
