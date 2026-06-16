<template>
  <div class="page-shell">
    <el-container style="min-height: 100vh">
      <el-aside width="260px" class="panel-card" style="margin: 20px; padding: 20px">
        <div class="shell-sidebar">
          <div>
            <h2 style="margin-top: 0">AutoBackup</h2>
            <p style="color: var(--text-muted); margin-bottom: 24px">自动备份与恢复控制台</p>
            <el-menu router :default-active="$route.path" style="border-right: none; background: transparent">
              <el-menu-item index="/">总览</el-menu-item>
              <el-menu-item index="/credentials">凭据</el-menu-item>
              <el-menu-item index="/buckets">存储桶</el-menu-item>
              <el-menu-item index="/tasks">备份任务</el-menu-item>
              <el-menu-item index="/artifacts">备份文件</el-menu-item>
              <el-menu-item index="/restore">恢复作业</el-menu-item>
              <el-menu-item index="/admin">管理员中心</el-menu-item>
              <el-menu-item index="/logs">日志中心</el-menu-item>
            </el-menu>
          </div>
          <el-button type="danger" plain style="width: 100%" @click="handleLogout">退出登录</el-button>
        </div>
      </el-aside>
      <el-main style="padding: 20px 20px 20px 0">
        <div class="panel-card" style="padding: 24px; min-height: calc(100vh - 40px)">
          <router-view />
        </div>
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const router = useRouter();

/**
 * Provide the shared admin shell layout with the side navigation.
 */

/**
 * Ask the user to confirm logout, then clear the local session and return to login.
 *
 * Returns:
 *   Promise that resolves after the logout flow finishes.
 */
async function handleLogout() {
  try {
    await ElMessageBox.confirm("退出后需要重新登录，是否继续？", "退出登录", {
      confirmButtonText: "退出",
      cancelButtonText: "取消",
      type: "warning"
    });
    authStore.logout();
    await router.replace("/login");
    ElMessage.success("已退出登录");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error("退出登录失败，请稍后重试");
    }
  }
}
</script>

<style scoped>
.shell-sidebar {
  min-height: calc(100vh - 80px);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 24px;
}
</style>
