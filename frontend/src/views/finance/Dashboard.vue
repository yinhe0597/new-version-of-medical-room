<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <el-menu
        :default-active="activeMenu"
        class="el-menu-vertical"
        router
      >
        <div class="logo">
          <h3>财务工作台</h3>
        </div>
        <el-menu-item index="/finance/dashboard">
          <el-icon><DataLine /></el-icon>
          <span>财务看板</span>
        </el-menu-item>
        <el-menu-item index="/finance/statistics">
          <el-icon><Coin /></el-icon>
          <span>营收统计报表</span>
        </el-menu-item>
        <el-menu-item index="/finance/drug-outbound-report">
          <el-icon><List /></el-icon>
          <span>药品出库报表</span>
        </el-menu-item>
        <el-menu-item index="/finance/drugs">
          <el-icon><FirstAidKit /></el-icon>
          <span>药品价格查看</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-content">
          <span>欢迎您，{{ userStore.userInfo.real_name }} 财务</span>
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
import { FirstAidKit, DataLine, Setting, User, Avatar, Coin, List } from '@element-plus/icons-vue'

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
