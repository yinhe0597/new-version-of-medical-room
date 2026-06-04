<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <el-menu
        :default-active="activeMenu"
        class="el-menu-vertical"
        router
      >
        <div class="logo">
          <h3>系统管理后台</h3>
        </div>
        <el-menu-item index="/admin/users">
          <el-icon><User /></el-icon>
          <span>账号管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/drugs">
          <el-icon><FirstAidKit /></el-icon>
          <span>药品管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/patients">
          <el-icon><Avatar /></el-icon>
          <span>人员档案管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/statistics">
          <el-icon><DataLine /></el-icon>
          <span>统计报表</span>
        </el-menu-item>
        <el-menu-item index="/admin/finance-dashboard">
          <el-icon><Coin /></el-icon>
          <span>财务看板</span>
        </el-menu-item>
        <el-menu-item index="/admin/drug-outbound-report">
          <el-icon><DataLine /></el-icon>
          <span>药品出库报表</span>
        </el-menu-item>
        <el-menu-item index="/admin/operation-log">
          <el-icon><Document /></el-icon>
          <span>运营日志</span>
        </el-menu-item>
        <el-menu-item index="/admin/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header class="header">
        <div class="header-content">
          <span>欢迎您，{{ userStore.userInfo.real_name }} 管理员</span>
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
import { FirstAidKit, DataLine, Setting, User, Avatar, Document, Coin } from '@element-plus/icons-vue'

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
  background-color: #303133;
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
