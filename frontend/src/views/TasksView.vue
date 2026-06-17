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
      <el-table-column type="expand">
        <template #default="{ row }">
          <div v-if="getLatestRun(row.id)" class="run-progress-panel">
            <div class="run-progress-header">
              <el-tag :type="statusTagTypeMap[getLatestRun(row.id).status] || 'info'">
                {{ formatRunStatus(getLatestRun(row.id)) }}
              </el-tag>
              <span class="run-progress-meta">
                {{ formatRunSource(getLatestRun(row.id)) }} / {{ getLatestRun(row.id).updated_at }}
              </span>
            </div>
            <div class="run-progress-step">{{ formatStepText(getLatestRun(row.id)) }}</div>
            <el-progress
              :percentage="getLatestRun(row.id).progress_percent"
              :status="getLatestRun(row.id).status === 'failed' ? 'exception' : undefined"
            />
            <div class="run-progress-detail">{{ formatProgressDetail(getLatestRun(row.id)) }}</div>
            <div v-if="getLatestRun(row.id).bucket_progresses.length" class="bucket-progress-list">
              <div
                v-for="bucketProgress in getLatestRun(row.id).bucket_progresses"
                :key="bucketProgress.id"
                class="bucket-progress-item"
              >
                <div class="bucket-progress-header">
                  <span>{{ bucketProgress.bucket_name }} ({{ bucketProgress.bucket_region }})</span>
                  <el-tag :type="statusTagTypeMap[bucketProgress.status] || 'info'" size="small">
                    {{ formatBucketStatus(bucketProgress.status) }}
                  </el-tag>
                </div>
                <el-progress
                  :percentage="bucketProgress.progress_percent"
                  :status="bucketProgress.status === 'failed' ? 'exception' : undefined"
                  :stroke-width="12"
                />
                <div class="run-progress-detail">{{ formatBucketProgressDetail(bucketProgress) }}</div>
                <div v-if="bucketProgress.error_message" class="run-progress-error">
                  {{ bucketProgress.error_message }}
                </div>
              </div>
            </div>
            <div v-if="getLatestRun(row.id).error_message" class="run-progress-error">
              {{ getLatestRun(row.id).error_message }}
            </div>
          </div>
          <el-empty v-else description="暂无执行记录" :image-size="72" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="任务名称" />
      <el-table-column prop="source_path" label="源目录" />
      <el-table-column label="调度配置">
        <template #default="{ row }">{{ formatSchedule(row) }}</template>
      </el-table-column>
      <el-table-column prop="bucket_ids" label="目标桶">
        <template #default="{ row }">{{ row.bucket_ids.join(", ") }}</template>
      </el-table-column>
      <el-table-column label="最近执行状态" min-width="280">
        <template #default="{ row }">
          <div v-if="getLatestRun(row.id)" class="table-run-summary">
            <el-tag :type="statusTagTypeMap[getLatestRun(row.id).status] || 'info'" size="small">
              {{ formatRunStatus(getLatestRun(row.id)) }}
            </el-tag>
            <span class="table-run-summary-text">{{ buildRunSummary(getLatestRun(row.id)) }}</span>
          </div>
          <span v-else>未执行</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" type="success" :disabled="isTaskBusy(row.id)" @click="runTask(row.id)">
            {{ isTaskBusy(row.id) ? "执行中" : "立即执行" }}
          </el-button>
          <el-button
            v-if="getLatestRun(row.id) && canCancelRun(getLatestRun(row.id))"
            size="small"
            type="danger"
            plain
            :disabled="isCancelPending(getLatestRun(row.id))"
            @click="cancelRunRequest(getLatestRun(row.id))"
          >
            {{ isCancelPending(getLatestRun(row.id)) ? "终止中" : "终止" }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
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
const statusTagTypeMap = {
  pending: "info",
  running: "warning",
  canceled: "info",
  success: "success",
  failed: "danger"
};
const buckets = ref([]);
const tasks = ref([]);
const runRequests = ref([]);
const runPollingTimer = ref(null);
const selectedWeekdays = computed({
  get() {
    return taskForm.weekday_mask ? taskForm.weekday_mask.split(",").filter(Boolean) : [];
  },
  set(value) {
    taskForm.weekday_mask = value.join(",");
  }
});
const latestRunMap = computed(() => {
  const latestMap = {};
  for (const runRequest of runRequests.value) {
    if (!latestMap[runRequest.task_id]) {
      latestMap[runRequest.task_id] = runRequest;
    }
  }
  return latestMap;
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
  [tasks.value, buckets.value, runRequests.value] = await Promise.all([
    request("/api/backup-tasks"),
    request("/api/cos/buckets"),
    request("/api/backup-run-requests")
  ]);
}

/**
 * Refresh only backup run progress data during the polling loop.
 *
 * Returns:
 *   Promise that resolves after recent run requests are fetched.
 */
async function refreshRunRequests() {
  runRequests.value = await request("/api/backup-run-requests");
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
    ElMessage.success("任务已保存并已进入执行队列");
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
    ElMessage.success("备份任务已进入执行队列");
    await refreshRunRequests();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Request safe termination for one queued or running backup job.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   Promise that resolves after the backend records the cancel request.
 */
async function cancelRunRequest(runRequest) {
  try {
    await request(`/api/backup-run-requests/${runRequest.id}/cancel`, {
      method: "POST"
    });
    ElMessage.success("已提交终止请求，系统将安全结束并清理当前作业");
    await refreshRunRequests();
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

/**
 * Return the most recent run request for one task.
 *
 * Args:
 *   taskId: Backup task primary key.
 *
 * Returns:
 *   Latest run request object or null when no runs exist.
 */
function getLatestRun(taskId) {
  return latestRunMap.value[taskId] || null;
}

/**
 * Check whether one task already has a queued or running backup.
 *
 * Args:
 *   taskId: Backup task primary key.
 *
 * Returns:
 *   True when the task currently has a queued or running execution.
 */
function isTaskBusy(taskId) {
  const latestRun = getLatestRun(taskId);
  return Boolean(latestRun && ["pending", "running"].includes(latestRun.status));
}

/**
 * Check whether one run request can still be canceled from the UI.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   True when the run is still queued or running.
 */
function canCancelRun(runRequest) {
  return ["pending", "running"].includes(runRequest.status);
}

/**
 * Check whether one run request already has a cancel request in progress.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   True when the operator already asked the backend to terminate the job.
 */
function isCancelPending(runRequest) {
  return Boolean(runRequest.cancel_requested);
}

/**
 * Convert one run request status into display text.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   Chinese status text string.
 */
function formatRunStatus(runRequest) {
  const statusTextMap = {
    pending: "排队中",
    running: "执行中",
    canceled: "已终止",
    success: "成功",
    failed: "失败"
  };
  if (runRequest.cancel_requested && runRequest.status === "running") {
    return "终止中";
  }
  return statusTextMap[runRequest.status] || runRequest.status;
}

/**
 * Convert one run request source into display text.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   Chinese trigger source label.
 */
function formatRunSource(runRequest) {
  return runRequest.trigger_source === "scheduler" ? "定时触发" : "手动触发";
}

/**
 * Convert one step code and message into a readable step summary.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   Readable step summary string.
 */
function formatStepText(runRequest) {
  const stepTextMap = {
    queued: "等待 worker 执行",
    cancel_requested: "正在安全终止当前作业",
    canceled: "备份作业已终止",
    scanning: "正在扫描源目录",
    compressing: "正在压缩文件",
    checksumming: "正在计算校验值",
    uploading: "正在上传压缩包",
    completed: "备份执行完成",
    failed: "备份执行失败"
  };
  return runRequest.step_message || stepTextMap[runRequest.current_step] || runRequest.current_step;
}

/**
 * Format one run request progress detail string.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   Detail string containing completed units and percent.
 */
function formatProgressDetail(runRequest) {
  if (runRequest.status === "canceled") {
    return runRequest.finished_at ? `终止完成时间: ${runRequest.finished_at}` : "备份作业已终止";
  }
  if (!runRequest.step_total || !runRequest.step_unit) {
    return runRequest.finished_at ? `完成时间: ${runRequest.finished_at}` : "等待更多进度数据";
  }
  return `${runRequest.step_completed} / ${runRequest.step_total} ${runRequest.step_unit} (${runRequest.progress_percent}%)`;
}

/**
 * Format one bucket upload status into display text.
 *
 * Args:
 *   status: Bucket upload status code.
 *
 * Returns:
 *   Chinese status text string.
 */
function formatBucketStatus(status) {
  const statusTextMap = {
    pending: "等待上传",
    running: "上传中",
    success: "上传成功",
    failed: "上传失败"
  };
  return statusTextMap[status] || status;
}

/**
 * Format one bucket progress detail string.
 *
 * Args:
 *   bucketProgress: One bucket progress row from the API.
 *
 * Returns:
 *   Detail string containing uploaded bytes and percent.
 */
function formatBucketProgressDetail(bucketProgress) {
  if (!bucketProgress.total_bytes) {
    return "等待上传开始";
  }
  return `${bucketProgress.uploaded_bytes} / ${bucketProgress.total_bytes} bytes (${bucketProgress.progress_percent}%)`;
}

/**
 * Build a compact task-table summary for the most recent run.
 *
 * Args:
 *   runRequest: Recent backup run request object.
 *
 * Returns:
 *   Short summary string suitable for a table cell.
 */
function buildRunSummary(runRequest) {
  if (runRequest.cancel_requested && ["pending", "running"].includes(runRequest.status)) {
    return "正在接收终止请求并清理现场";
  }
  return `${formatStepText(runRequest)} / ${runRequest.progress_percent}%`;
}

/**
 * Start the run-progress polling timer.
 *
 * Returns:
 *   None. A repeating timer is registered until the view is unmounted.
 */
function startRunPolling() {
  stopRunPolling();
  runPollingTimer.value = window.setInterval(async () => {
    try {
      await refreshRunRequests();
    } catch (_) {
      // Ignore transient polling failures and keep the next polling cycle alive.
    }
  }, 3000);
}

/**
 * Stop the run-progress polling timer when the view is destroyed.
 *
 * Returns:
 *   None. The timer is cleared when present.
 */
function stopRunPolling() {
  if (runPollingTimer.value) {
    window.clearInterval(runPollingTimer.value);
    runPollingTimer.value = null;
  }
}

onMounted(async () => {
  await loadData();
  startRunPolling();
});

onUnmounted(() => {
  stopRunPolling();
});
</script>

<style scoped>
.task-actions {
  display: flex;
  gap: 12px;
}

.table-run-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.table-run-summary-text {
  color: #4b5563;
  line-height: 1.4;
}

.run-progress-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}

.run-progress-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.run-progress-meta {
  color: #6b7280;
  font-size: 13px;
}

.run-progress-step {
  font-weight: 600;
  color: #111827;
}

.run-progress-detail {
  color: #4b5563;
  font-size: 13px;
}

.run-progress-error {
  color: #dc2626;
  font-size: 13px;
  line-height: 1.5;
}

.bucket-progress-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bucket-progress-item {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #f9fafb;
}

.bucket-progress-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
</style>
