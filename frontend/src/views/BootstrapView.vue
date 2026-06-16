<template>
  <div>
    <h1 class="view-title">首次安全初始化</h1>
    <el-row :gutter="24">
      <el-col :md="12" :span="24">
        <el-card shadow="never">
          <template #header>修改默认凭据</template>
          <el-form label-position="top">
            <el-form-item label="新用户名">
              <el-input v-model="bootstrapForm.username" />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="bootstrapForm.password" type="password" show-password />
            </el-form-item>
            <el-button type="primary" @click="completeBootstrap">提交</el-button>
          </el-form>
        </el-card>
      </el-col>
      <el-col :md="12" :span="24">
        <el-card shadow="never">
          <template #header>TOTP 配置</template>
          <el-button @click="beginTotpSetup">生成 TOTP 配置</el-button>
          <div v-if="totpSetup" style="margin-top: 16px">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="Secret">{{ totpSetup.secret }}</el-descriptions-item>
              <el-descriptions-item label="URI">{{ totpSetup.otpauth_uri }}</el-descriptions-item>
            </el-descriptions>
            <el-input v-model="totpCode" placeholder="输入当前验证码" style="margin-top: 16px" />
            <el-button type="success" style="margin-top: 12px" @click="confirmTotp">确认启用 TOTP</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" style="margin-top: 24px">
      <template #header>Passkey 配置</template>
      <el-form inline>
        <el-form-item label="Passkey 名称">
          <el-input v-model="passkeyName" placeholder="例如 MacBook Touch ID" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" plain @click="registerPasskey">添加 Passkey</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { request } from "../api/http";
import { useAuthStore } from "../stores/auth";
import { normalizeRegistrationOptions, serializeRegistrationCredential } from "../utils/webauthn";

const router = useRouter();
const authStore = useAuthStore();
const bootstrapForm = reactive({
  username: "",
  password: ""
});
const totpSetup = ref(null);
const totpCode = ref("");
const passkeyName = ref("Primary Passkey");

/**
 * Complete the first-run credential rotation.
 *
 * Returns:
 *   Promise that resolves after the backend stores the new credentials.
 */
async function completeBootstrap() {
  try {
    await request("/api/admin/bootstrap/complete", {
      method: "POST",
      body: JSON.stringify(bootstrapForm)
    });
    ElMessage.success("默认凭据已替换");
    await authStore.loadBootstrapStatus();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Request new TOTP enrollment material from the backend.
 *
 * Returns:
 *   Promise that resolves after the secret and URI are loaded.
 */
async function beginTotpSetup() {
  try {
    totpSetup.value = await request("/api/admin/totp/setup", { method: "POST" });
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Confirm TOTP setup and redirect to the dashboard when bootstrap is complete.
 *
 * Returns:
 *   Promise that resolves after the backend enables TOTP.
 */
async function confirmTotp() {
  try {
    await request("/api/admin/totp/confirm", {
      method: "POST",
      body: JSON.stringify({
        setup_token: totpSetup.value.setup_token,
        code: totpCode.value
      })
    });
    ElMessage.success("TOTP 已启用");
    await authStore.loadBootstrapStatus();
    if (!authStore.bootstrapStatus?.must_bootstrap) {
      router.push("/");
    }
  } catch (error) {
    ElMessage.error(error.message);
  }
}

/**
 * Register a browser Passkey during the bootstrap flow.
 *
 * Returns:
 *   Promise that resolves after the backend stores the verified Passkey.
 */
async function registerPasskey() {
  try {
    const optionsResponse = await request("/api/admin/passkeys/register/options", {
      method: "POST",
      body: JSON.stringify({ friendly_name: passkeyName.value })
    });
    const credential = await navigator.credentials.create({
      publicKey: normalizeRegistrationOptions(optionsResponse.public_key)
    });
    await request("/api/admin/passkeys/register/verify", {
      method: "POST",
      body: JSON.stringify({
        challenge_token: optionsResponse.challenge_token,
        credential: serializeRegistrationCredential(credential)
      })
    });
    ElMessage.success("Passkey 已启用");
    await authStore.loadBootstrapStatus();
    if (!authStore.bootstrapStatus?.must_bootstrap) {
      router.push("/");
    }
  } catch (error) {
    ElMessage.error(error.message || "Passkey 注册失败");
  }
}
</script>
