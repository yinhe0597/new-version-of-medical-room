<template>
  <div class="account-settings">
    <el-card>
      <template #header>
        <span>账号设置</span>
      </template>
      <el-form class="account-form" label-width="100px">
        <el-form-item label="登录账号">
          <span>{{ userStore.userInfo.username || '-' }}</span>
        </el-form-item>
        <el-form-item label="姓名">
          <span>{{ userStore.userInfo.real_name || '-' }}</span>
        </el-form-item>
        <el-form-item label="角色">
          <span>{{ roleLabel }}</span>
        </el-form-item>
        <el-divider />
        <el-form-item label="登录密码">
          <ChangePassword />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ChangePassword from '@/components/ChangePassword.vue'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const roleLabels = {
  doctor: '医生',
  nurse: '护士',
  finance: '财务',
  admin: '管理员'
}
const roleLabel = computed(() => roleLabels[userStore.userInfo.role] || '-')
</script>

<style scoped>
.account-settings {
  width: 100%;
  max-width: 640px;
  padding: 20px;
  box-sizing: border-box;
}

@media (max-width: 600px) {
  .account-settings {
    padding: 0;
  }

  :deep(.account-form .el-form-item) {
    display: block;
  }

  :deep(.account-form .el-form-item__label) {
    width: auto !important;
    height: auto;
    justify-content: flex-start;
    margin-bottom: 6px;
  }

  :deep(.account-form .el-form-item__content) {
    margin-left: 0 !important;
    overflow-wrap: anywhere;
  }
}
</style>
