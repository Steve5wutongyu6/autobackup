<template>
  <div class="page-shell" style="display: grid; place-items: center; padding: 24px">
    <div class="panel-card" style="width: min(460px, 100%); padding: 32px">
      <h1 class="view-title">管理员登录</h1>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" show-password type="password" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" @click="handleLogin">
          继续
        </el-button>
      </el-form>

      <div v-if="authStore.challenge && !authStore.challenge?.methods?.includes('bootstrap')" style="margin-top: 24px">
        <el-alert
          title="密码校验已通过，请完成第二因素验证"
          type="success"
          :closable="false"
          style="margin-bottom: 16px"
        />
        <el-form label-position="top" @submit.prevent>
          <el-form-item v-if="authStore.challenge?.methods?.includes('totp')" label="TOTP 验证码">
            <el-input v-model="totpCode" maxlength="8" />
          </el-form-item>
          <el-button
            v-if="authStore.challenge?.methods?.includes('totp')"
            type="success"
            style="width: 100%"
            @click="handleTotpVerify"
          >
            使用 TOTP 登录
          </el-button>
          <el-button
            v-if="authStore.challenge?.methods?.includes('passkey')"
            type="primary"
            plain
            style="width: 100%; margin-top: 12px"
            @click="handlePasskeyVerify"
          >
            使用 Passkey 登录
          </el-button>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { request } from "../api/http";
import { useAuthStore } from "../stores/auth";
import { normalizeAuthenticationOptions, serializeAuthenticationCredential } from "../utils/webauthn";

const authStore = useAuthStore();
const router = useRouter();
const form = reactive({
  username: "",
  password: ""
});
const totpCode = ref("");

/**
 * Start the password stage of the login flow.
 *
 * Returns:
 *   Promise that resolves after the login challenge is created.
 */
async function handleLogin() {
  try {
    await authStore.login(form.username, form.password);
    if (authStore.challenge?.methods?.includes("bootstrap")) {
      ElMessage.success("密码校验通过，请继续完成首次初始化");
      router.push("/bootstrap");
      return;
    }
    ElMessage.success("密码已校验，请完成二次验证");
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Complete the TOTP stage of login and enter the admin UI.
 *
 * Returns:
 *   Promise that resolves after successful authentication.
 */
async function handleTotpVerify() {
  try {
    await authStore.verifyTotp(totpCode.value);
    await authStore.loadBootstrapStatus();
    router.push(authStore.bootstrapStatus?.must_bootstrap ? "/bootstrap" : "/");
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Complete the Passkey stage of login through the browser WebAuthn API.
 *
 * Returns:
 *   Promise that resolves after successful Passkey authentication.
 */
async function handlePasskeyVerify() {
  try {
    const optionsResponse = await request("/api/auth/2fa/passkey/options", {
      method: "POST",
      body: JSON.stringify({
        challenge_token: authStore.challenge?.challenge_token
      })
    });
    const credential = await navigator.credentials.get({
      publicKey: normalizeAuthenticationOptions(optionsResponse.public_key)
    });
    const tokenPair = await request("/api/auth/2fa/passkey/verify", {
      method: "POST",
      body: JSON.stringify({
        challenge_token: optionsResponse.challenge_token,
        credential: serializeAuthenticationCredential(credential)
      })
    });
    authStore.setSession(tokenPair.access_token, tokenPair.refresh_token);
    await authStore.loadBootstrapStatus();
    router.push(authStore.bootstrapStatus?.must_bootstrap ? "/bootstrap" : "/");
  } catch (error) {
    ElMessage.error(error.message || "Passkey 登录失败");
  }
}
</script>
