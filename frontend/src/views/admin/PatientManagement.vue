<template>
  <div class="patient-management-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>学生(患者)档案批量导入</span>
          <el-button type="primary" @click="downloadTemplate">下载 CSV 模板</el-button>
        </div>
      </template>
      <div class="import-section">
        <el-upload
          class="upload-demo"
          drag
          :action="uploadUrl"
          :headers="headers"
          :on-success="handleSuccess"
          :on-error="handleError"
          :before-upload="beforeUpload"
          accept=".csv"
          :limit="1"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            将文件拖到此处，或 <em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              只能上传 csv 文件，且文件内容需严格按照模板格式。对于已存在的学号会进行更新操作。
            </div>
          </template>
        </el-upload>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

// Use full URL or proxy path for upload action
const uploadUrl = computed(() => {
  return import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL + '/admin/patients/import' : '/api/admin/patients/import'
})

const headers = computed(() => {
  const token = localStorage.getItem('token')
  return {
    Authorization: `Bearer ${token}`
  }
})

const downloadTemplate = async () => {
  try {
    const res = await request.get('/admin/patients/template', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'patients_template.csv')
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch (error) {
    ElMessage.error('模板下载失败')
  }
}

const beforeUpload = (file) => {
  const isCsv = file.name.endsWith('.csv') || file.type === 'text/csv'
  if (!isCsv) {
    ElMessage.error('上传文件只能是 CSV 格式!')
  }
  return isCsv
}

const handleSuccess = (response, uploadFile) => {
  ElMessage.success(response.msg || '导入成功')
}

const handleError = (error, uploadFile) => {
  try {
    const res = JSON.parse(error.message)
    ElMessage.error(res.msg || '导入失败')
  } catch (e) {
    ElMessage.error('导入失败')
  }
}
</script>

<style scoped>
.patient-management-container {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.import-section {
  margin-top: 20px;
  text-align: center;
}
</style>
