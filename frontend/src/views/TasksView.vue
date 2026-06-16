<template>
  <div>
    <h1 class="view-title">备份任务</h1>
    <el-card shadow="never">
      <el-form label-position="top">
        <el-row :gutter="20">
          <el-col :md="8" :span="24">
            <el-form-item label="任务名称">
              <el-input v-model="taskForm.name" />
            </el-form-item>
          </el-col>
          <el-col :md="8" :span="24">
            <el-form-item label="源目录">
              <el-input v-model="taskForm.source_path" placeholder="/data/example" />
            </el-form-item>
          </el-col>
          <el-col :md="8" :span="24">
            <el-form-item label="ZIP 密码">
              <el-input v-model="taskForm.zip_password" type="password" show-password />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :md="6" :span="24">
            <el-form-item label="调度类型">
              <el-select v-model="taskForm.schedule_type" style="width: 100%">
                <el-option label="固定间隔" value="interval" />
                <el-option label="固定星期" value="weekly" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :md="6" :span="24">
            <el-form-item label="间隔分钟">
              <el-input-number v-model="taskForm.interval_minutes" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :md="6" :span="24">
            <el-form-item label="星期掩码">
              <el-input v-model="taskForm.weekday_mask" placeholder="mon,wed,fri" />
            </el-form-item>
          </el-col>
          <el-col :md="6" :span="24">
            <el-form-item label="执行时间">
              <el-time-picker v-model="taskForm.run_time" value-format="HH:mm:ss" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="目标存储桶">
          <el-select v-model="taskForm.bucket_ids" multiple style="width: 100%">
            <el-option v-for="bucket in buckets" :key="bucket.id" :label="`${bucket.name} (${bucket.region})`" :value="bucket.id" />
          </el-select>
        </el-form-item>
        <el-button type="primary" @click="saveTask">保存任务</el-button>
      </el-form>
    </el-card>
    <el-table :data="tasks" style="margin-top: 24px" border>
      <el-table-column prop="name" label="任务名称" />
      <el-table-column prop="source_path" label="源目录" />
      <el-table-column prop="schedule_type" label="调度类型" />
      <el-table-column prop="bucket_ids" label="目标桶">
        <template #default="{ row }">{{ row.bucket_ids.join(", ") }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="runTask(row.id)">立即执行</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { request } from "../api/http";

const buckets = ref([]);
const tasks = ref([]);
const taskForm = reactive({
  name: "",
  source_path: "",
  zip_password: "",
  schedule_type: "interval",
  interval_minutes: 60,
  weekday_mask: "mon",
  run_time: "03:00:00",
  enabled: true,
  bucket_ids: []
});

/**
 * Load task and bucket data for the task management view.
 *
 * Returns:
 *   Promise that resolves after both lists are loaded.
 */
async function loadData() {
  [tasks.value, buckets.value] = await Promise.all([
    request("/api/backup-tasks"),
    request("/api/cos/buckets")
  ]);
}

/**
 * Save the current task form as a backup task.
 *
 * Returns:
 *   Promise that resolves after the task is stored and lists are refreshed.
 */
async function saveTask() {
  try {
    await request("/api/backup-tasks", {
      method: "POST",
      body: JSON.stringify(taskForm)
    });
    ElMessage.success("任务已保存");
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Trigger a backup task immediately.
 *
 * Args:
 *   taskId: Backup task primary key.
 *
 * Returns:
 *   Promise that resolves after the backend creates a backup artifact.
 */
async function runTask(taskId) {
  try {
    await request(`/api/backup-tasks/${taskId}/run`, {
      method: "POST"
    });
    ElMessage.success("备份任务已触发");
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(loadData);
</script>
