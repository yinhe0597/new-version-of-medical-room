<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <el-menu
        :default-active="activeMenu"
        class="el-menu-vertical"
        router
      >
        <div class="logo">
          <h3>医生工作站</h3>
        </div>
        <el-sub-menu index="patient-reception">
          <template #title>
            <el-icon><User /></el-icon>
            <span>患者接诊</span>
          </template>
          <el-menu-item index="/doctor/patient">
            <span>接诊</span>
          </el-menu-item>
          <el-menu-item index="/doctor/templates/chief-complaint">
            <span>主诉模板</span>
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
import { computed } from 'vue'
import { useUserStore } from '@/store/user'
import { useRouter, useRoute } from 'vue-router'
import { User, List, ShoppingCart } from '@element-plus/icons-vue'

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
.el-menu-vertical {
  height: 100%;
  border-right: 1px solid #dcdfe6;
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
