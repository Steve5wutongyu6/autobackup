<template>
  <div>
    <h1 class="view-title">总览</h1>
    <el-row :gutter="20">
      <el-col :lg="8" :span="24">
        <el-card shadow="never">
          <div>存储桶数量</div>
          <h2>{{ buckets.length }}</h2>
        </el-card>
      </el-col>
      <el-col :lg="8" :span="24">
        <el-card shadow="never">
          <div>备份任务数量</div>
          <h2>{{ tasks.length }}</h2>
        </el-card>
      </el-col>
      <el-col :lg="8" :span="24">
        <el-card shadow="never">
          <div>逻辑备份数量</div>
          <h2>{{ artifacts.length }}</h2>
        </el-card>
      </el-col>
    </el-row>
    <el-alert
      title="下载或恢复前会先重新检测 COS 是否走内网。若检测到公网路径，系统会暂停并要求明确确认。"
      type="warning"
      :closable="false"
      style="margin-top: 24px"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";

import { request } from "../api/http";

const buckets = ref([]);
const tasks = ref([]);
const artifacts = ref([]);

/**
 * Load dashboard summary data from the backend.
 *
 * Returns:
 *   Promise that resolves after all summary lists are fetched.
 */
async function loadDashboard() {
  [buckets.value, tasks.value, artifacts.value] = await Promise.all([
    request("/api/cos/buckets"),
    request("/api/backup-tasks"),
    request("/api/artifacts")
  ]);
}

onMounted(loadDashboard);
</script>
