<template>
  <div class="settings-container">
    <el-card>
      <template #header>
        <span>系统设置</span>
      </template>
      
      <el-form label-width="120px">
        <el-form-item label="数据备份">
          <el-button type="primary" :icon="DocumentCopy" @click="handleBackup" :loading="backingUp">
            一键备份数据
          </el-button>
          <div class="tip">系统将下载 SQLite (.db)，或包含 SQL 与校验清单的 MySQL ZIP 备份。</div>
        </el-form-item>
        
        <el-divider />
        
        <el-form-item label="修改密码">
          <ChangePassword />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import request from '@/api/request'
import ChangePassword from '@/components/ChangePassword.vue'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const backingUp = ref(false)

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0)
}

const responseFilename = (header, fallback) => {
  if (!header) return fallback
  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]).replace(/[\\/:*?"<>|]/g, '_')
    } catch {
      return fallback
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i)
  return plain ? plain[1].replace(/[\\/:*?"<>|]/g, '_') : fallback
}

const blobSha256 = async blob => {
  if (!window.crypto || !window.crypto.subtle) {
    throw { msg: '当前浏览器无法校验备份摘要，请使用支持 Web Crypto 的 HTTPS 环境' }
  }
  const digest = await window.crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  return Array.from(new Uint8Array(digest))
    .map(value => value.toString(16).padStart(2, '0'))
    .join('')
}

const handleBackup = async () => {
  backingUp.value = true
  try {
    const res = await request.get('/admin/backup', {
      responseType: 'blob',
      timeout: 300000,
      returnFullResponse: true
    })

    const blobData = res.data
    if (blobData.type && blobData.type.includes('application/json')) {
       // If it's json, it might be an error message
       const reader = new FileReader()
       reader.onload = () => {
         const errorData = JSON.parse(reader.result)
         ElMessage.error(errorData.msg || '备份失败')
       }
       reader.readAsText(blobData)
       return
    }

    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').split('.')[0]
    const isSqlite = Boolean(blobData.type && blobData.type.includes('sqlite'))
    const extension = isSqlite ? 'db' : 'zip'
    const filename = responseFilename(
      res.headers['content-disposition'],
      `medical_db_backup_${timestamp}.${extension}`
    )

    if (!isSqlite) {
      const bundleSha256 = String(
        res.headers['x-backup-bundle-sha256'] || ''
      ).toLowerCase()
      if (!/^[0-9a-f]{64}$/.test(bundleSha256)) {
        throw { msg: '备份响应缺少 ZIP 完整性摘要，文件未保存' }
      }
      const actualDigest = await blobSha256(blobData)
      if (actualDigest !== bundleSha256) {
        throw { msg: '备份 ZIP 下载内容校验失败，文件未保存' }
      }
      downloadBlob(blobData, filename)
      ElMessage.success(`备份 ZIP 已校验并开始下载，SHA-256：${bundleSha256}`)
    } else {
      downloadBlob(blobData, filename)
      ElMessage.success('备份已生成并开始下载')
    }
  } catch (error) {
    ElMessage.error(error.msg || '备份失败')
  } finally {
    backingUp.value = false
  }
}

</script>

<style scoped>
.settings-container {
  padding: 20px;
  max-width: 600px;
}
.tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}
</style>
