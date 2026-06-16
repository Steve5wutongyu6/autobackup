import { createRouter, createWebHistory } from "vue-router";

import DashboardView from "../views/DashboardView.vue";
import LoginView from "../views/LoginView.vue";
import ShellLayout from "../views/ShellLayout.vue";
import BootstrapView from "../views/BootstrapView.vue";
import BucketsView from "../views/BucketsView.vue";
import TasksView from "../views/TasksView.vue";
import ArtifactsView from "../views/ArtifactsView.vue";
import AdminView from "../views/AdminView.vue";
import LogsView from "../views/LogsView.vue";
import RestoreView from "../views/RestoreView.vue";
import { useAuthStore } from "../stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginView },
    {
      path: "/",
      component: ShellLayout,
      children: [
        { path: "", component: DashboardView },
        { path: "bootstrap", component: BootstrapView },
        { path: "buckets", component: BucketsView },
        { path: "tasks", component: TasksView },
        { path: "artifacts", component: ArtifactsView },
        { path: "restore", component: RestoreView },
        { path: "admin", component: AdminView },
        { path: "logs", component: LogsView }
      ]
    }
  ]
});

/**
 * Protect authenticated routes and redirect unauthenticated users to login.
 *
 * Args:
 *   to: Target route.
 *   _from: Previous route.
 *   next: Router continuation callback.
 *
 * Returns:
 *   None. Navigation is redirected or allowed through the callback.
 */
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore();
  if (!authStore.bootstrapStatus) {
    try {
      await authStore.loadBootstrapStatus();
    } catch (_) {
      if (to.path !== "/login") {
        next("/login");
        return;
      }
    }
  }
  if (to.path === "/login") {
    next();
    return;
  }
  if (to.path === "/bootstrap" && authStore.hasBootstrapSession) {
    next();
    return;
  }
  if (!authStore.isAuthenticated) {
    next("/login");
    return;
  }
  if (authStore.bootstrapStatus?.must_bootstrap && to.path !== "/bootstrap") {
    next("/bootstrap");
    return;
  }
  next();
});

export default router;
