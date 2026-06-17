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
          <el-col :md="8" :span="24">
            <el-form-item label="调度类型">
              <el-select v-model="taskForm.schedule_type" style="width: 100%" @change="handleScheduleTypeChange">
                <el-option label="固定间隔" value="interval" />
                <el-option label="固定星期" value="weekly" />
                <el-option label="单次任务" value="once" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col v-if="taskForm.schedule_type === 'interval'" :md="8" :span="24">
            <el-form-item label="间隔分钟">
              <el-input-number v-model="taskForm.interval_minutes" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col v-if="taskForm.schedule_type === 'weekly'" :md="8" :span="24">
            <el-form-item label="星期几">
              <el-select v-model="selectedWeekdays" multiple collapse-tags collapse-tags-tooltip style="width: 100%">
                <el-option v-for="weekday in weekdayOptions" :key="weekday.value" :label="weekday.label" :value="weekday.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col v-if="taskForm.schedule_type === 'weekly'" :md="8" :span="24">
            <el-form-item label="执行时间">
              <el-time-picker v-model="taskForm.run_time" value-format="HH:mm:ss" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col v-if="taskForm.schedule_type === 'once'" :md="8" :span="24">
            <el-form-item label="执行日期时间">
              <el-date-picker
                v-model="taskForm.scheduled_at"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="目标存储桶">
          <el-select v-model="taskForm.bucket_ids" multiple style="width: 100%">
            <el-option
              v-for="bucket in buckets"
              :key="bucket.id"
              :label="`${bucket.name} (${bucket.region})`"
              :value="bucket.id"
            />
          </el-select>
        </el-form-item>
        <div class="task-actions">
          <el-button type="primary" @click="saveTask">保存任务</el-button>
          <el-button type="success" plain @click="saveAndRunTask">保存并立即执行一次</el-button>
        </div>
      </el-form>
    </el-card>
    <el-table :data="tasks" style="margin-top: 24px" border>
      <el-table-column prop="name" label="任务名称" />
      <el-table-column prop="source_path" label="源目录" />
      <el-table-column label="调度配置">
        <template #default="{ row }">{{ formatSchedule(row) }}</template>
      </el-table-column>
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { request } from "../api/http";

const weekdayOptions = [
  { label: "周一", value: "mon" },
  { label: "周二", value: "tue" },
  { label: "周三", value: "wed" },
  { label: "周四", value: "thu" },
  { label: "周五", value: "fri" },
  { label: "周六", value: "sat" },
  { label: "周日", value: "sun" }
];
const weekdayLabelMap = Object.fromEntries(weekdayOptions.map((item) => [item.value, item.label]));
const buckets = ref([]);
const tasks = ref([]);
const selectedWeekdays = computed({
  get() {
    return taskForm.weekday_mask ? taskForm.weekday_mask.split(",").filter(Boolean) : [];
  },
  set(value) {
    taskForm.weekday_mask = value.join(",");
  }
});
const taskForm = reactive({
  name: "",
  source_path: "",
  zip_password: "",
  schedule_type: "interval",
  interval_minutes: 60,
  weekday_mask: "mon",
  run_time: "03:00:00",
  scheduled_at: "",
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
 * Adjust form-only schedule fields after the operator switches schedule mode.
 *
 * Args:
 *   scheduleType: Selected schedule type string.
 *
 * Returns:
 *   None. Irrelevant fields are cleared to avoid sending conflicting values.
 */
function handleScheduleTypeChange(scheduleType) {
  if (scheduleType === "interval") {
    taskForm.weekday_mask = "mon";
    taskForm.run_time = "03:00:00";
    taskForm.scheduled_at = "";
    return;
  }
  if (scheduleType === "weekly") {
    taskForm.interval_minutes = 60;
    taskForm.scheduled_at = "";
    if (!taskForm.weekday_mask) {
      taskForm.weekday_mask = "mon";
    }
    if (!taskForm.run_time) {
      taskForm.run_time = "03:00:00";
    }
    return;
  }
  taskForm.interval_minutes = 60;
  taskForm.weekday_mask = "";
  taskForm.run_time = "";
}

/**
 * Build a clean request payload from the current form state.
 *
 * Returns:
 *   Task payload object ready for the backend API.
 */
function buildTaskPayload() {
  if (taskForm.schedule_type === "interval") {
    return {
      ...taskForm,
      weekday_mask: null,
      run_time: null,
      scheduled_at: null
    };
  }
  if (taskForm.schedule_type === "weekly") {
    return {
      ...taskForm,
      interval_minutes: null,
      scheduled_at: null
    };
  }
  return {
    ...taskForm,
    interval_minutes: null,
    weekday_mask: null,
    run_time: null
  };
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
      body: JSON.stringify(buildTaskPayload())
    });
    ElMessage.success("任务已保存");
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Save the current task configuration and trigger it once immediately.
 *
 * Returns:
 *   Promise that resolves after the task is saved and one run is started.
 */
async function saveAndRunTask() {
  try {
    const savedTask = await request("/api/backup-tasks", {
      method: "POST",
      body: JSON.stringify(buildTaskPayload())
    });
    await request(`/api/backup-tasks/${savedTask.id}/run`, {
      method: "POST"
    });
    ElMessage.success("任务已保存并开始执行");
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Trigger a backup task immediately from the saved task list.
 *
 * Args:
 *   taskId: Backup task primary key.
 *
 * Returns:
 *   Promise that resolves after the backend starts one backup run.
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

/**
 * Format one task schedule into a readable summary string for the table.
 *
 * Args:
 *   task: Task row object returned by the backend.
 *
 * Returns:
 *   Human-readable schedule description string.
 */
function formatSchedule(task) {
  if (task.schedule_type === "interval") {
    return `固定间隔 / 每 ${task.interval_minutes} 分钟`;
  }
  if (task.schedule_type === "weekly") {
    const weekdayText = (task.weekday_mask || "")
      .split(",")
      .filter(Boolean)
      .map((item) => weekdayLabelMap[item] || item)
      .join("、");
    return `固定星期 / ${weekdayText} ${task.run_time || ""}`.trim();
  }
  if (task.schedule_type === "once") {
    return `单次任务 / ${task.scheduled_at || "未设定"}`;
  }
  return task.schedule_type;
}

onMounted(loadData);
</script>

<style scoped>
.task-actions {
  display: flex;
  gap: 12px;
}
</style>
