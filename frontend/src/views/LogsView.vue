<template>
  <div>
    <h1 class="view-title">日志中心</h1>
    <el-tabs>
      <el-tab-pane label="审计日志">
        <el-table :data="auditLogs" border>
          <el-table-column prop="created_at" label="时间" />
          <el-table-column prop="action" label="动作" />
          <el-table-column prop="actor" label="操作者" />
          <el-table-column prop="outcome" label="结果" />
          <el-table-column prop="detail" label="详情" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="系统日志">
        <el-table :data="appLogs" border>
          <el-table-column prop="created_at" label="时间" />
          <el-table-column prop="level" label="级别" />
          <el-table-column prop="module" label="模块" />
          <el-table-column prop="message" label="消息" />
          <el-table-column prop="detail" label="详情" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";

import { request } from "../api/http";

const auditLogs = ref([]);
const appLogs = ref([]);

/**
 * Load audit and system logs for the log center.
 *
 * Returns:
 *   Promise that resolves after both log datasets are fetched.
 */
async function loadLogs() {
  [auditLogs.value, appLogs.value] = await Promise.all([
    request("/api/logs/audit"),
    request("/api/logs/system")
  ]);
}

onMounted(loadLogs);
</script>
