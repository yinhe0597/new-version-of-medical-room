<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <el-menu
        :default-active="activeMenu"
        class="el-menu-vertical"
        router
      >
        <div class="logo">
          <h3>护士工作站</h3>
        </div>
        <el-menu-item index="/nurse/pending">
          <el-icon><Timer /></el-icon>
          <span>待处置处方</span>
        </el-menu-item>
        <el-menu-item index="/nurse/inventory">
          <el-icon><Box /></el-icon>
          <span>库存盘点</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header class="header">
        <div class="header-content">
          <span>欢迎您，{{ userStore.userInfo.real_name }} 护士</span>
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
import { Timer, Box } from '@element-plus/icons-vue'

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
  background-color: #67c23a;
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
