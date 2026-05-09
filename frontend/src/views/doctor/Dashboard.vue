<template>
  <el-container class="layout-container">
    <el-aside :width="isCollapsed ? '64px' : '200px'">
      <el-menu
        :default-active="activeMenu"
        class="el-menu-vertical"
        router
        :collapse="isCollapsed"
      >
        <div class="logo">
          <h3 v-if="!isCollapsed">医生工作站</h3>
          <el-icon v-else :size="24"><User /></el-icon>
        </div>
        <el-button :icon="isCollapsed ? Expand : Fold" @click="isCollapsed = !isCollapsed" style="width: 100%; border: none; border-radius: 0;" />
        <el-sub-menu index="patient-reception">
          <template #title>
            <el-icon><User /></el-icon>
            <span>患者接诊</span>
          </template>
          <el-menu-item index="/doctor/patient">
            <span>接诊</span>
          </el-menu-item>
          <el-menu-item index="/doctor/templates/present-illness">
            <span>现病史模板</span>
          </el-menu-item>
          <el-menu-item index="/doctor/templates/physical-exam">
            <span>体格检查模板</span>
          </el-menu-item>
          <el-menu-item index="/doctor/templates/doctor-advice">
            <span>医生贴士模板</span>
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/doctor/direct-purchase">
          <el-icon><ShoppingCart /></el-icon>
          <span>单独购药</span>
        </el-menu-item>
        <el-menu-item index="/doctor/history">
          <el-icon><List /></el-icon>
          <span>历史记录</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header class="header">
        <div class="header-content">
          <span>欢迎您，{{ userStore.userInfo.real_name }} 医生</span>
          <el-button type="danger" link @click="logout">退出登录</el-button>
        </div>
      </el-header>
      
      <el-main>
        <router-view></router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useUserStore } from '@/store/user'
import { useRouter, useRoute } from 'vue-router'
import { User, List, ShoppingCart, Expand, Fold } from '@element-plus/icons-vue'

const isCollapsed = ref(false)

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const activeMenu = computed(() => route.path)

const logout = () => {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.el-aside {
  transition: width 0.3s ease;
  overflow: hidden;
}
.el-menu-vertical {
  height: 100%;
  border-right: 1px solid #dcdfe6;
}
.el-menu-vertical:not(.el-menu--collapse) {
  width: 200px;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #409eff;
  color: white;
}
.header {
  border-bottom: 1px solid #dcdfe6;
  background-color: white;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.header-content {
  display: flex;
  align-items: center;
  gap: 20px;
}
</style>
