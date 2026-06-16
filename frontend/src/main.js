import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import App from "./App.vue";
import router from "./router";
import "./styles/main.css";

/**
 * Boot the Vue application with Pinia, Router, and Element Plus.
 *
 * Returns:
 *   None. The app is mounted to the root DOM node.
 */
const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(ElementPlus);
app.mount("#app");

