<template>
  <div class="page-shell">
    <el-container style="min-height: 100vh">
      <el-aside width="260px" class="panel-card" style="margin: 20px; padding: 20px">
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
/**
 * Provide the shared admin shell layout with the side navigation.
 */
</script>
