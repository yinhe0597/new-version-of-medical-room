<template>
  <div class="user-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="left-panel">
            <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增账号</el-button>
          </div>
        </div>
      </template>

      <el-table :data="userList" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="username" label="登录账号" />
        <el-table-column prop="real_name" label="真实姓名" />
        <el-table-column prop="role" label="角色">
          <template #default="scope">
            <el-tag :type="scope.row.role === 'doctor' ? 'success' : scope.row.role === 'nurse' ? 'info' : 'warning'">
              {{ scope.row.role === 'doctor' ? '医生' : scope.row.role === 'nurse' ? '护士' : '财务' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button 
              size="small" 
              type="danger" 
              @click="handleDelete(scope.row)" 
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 账号表单弹窗 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="isEdit ? '编辑账号' : '新增账号'" 
      width="400px"
    >
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="form.role">
            <el-radio label="doctor">医生</el-radio>
            <el-radio label="nurse">护士</el-radio>
            <el-radio label="finance">财务</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="登录账号" prop="username">
          <el-input v-model="form.username" placeholder="请输入登录账号"></el-input>
        </el-form-item>
        <el-form-item label="真实姓名" prop="real_name">
          <el-input v-model="form.real_name" placeholder="请输入真实姓名"></el-input>
        </el-form-item>
        <el-form-item label="登录密码" prop="password">
          <el-input v-model="form.password" type="password" :placeholder="isEdit ? '不修改请留空' : '请输入登录密码'" show-password></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const userList = ref([])
const loading = ref(false)

const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const formRef = ref(null)

const form = ref({
  id: null,
  username: '',
  real_name: '',
  role: 'doctor',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入登录账号', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入真实姓名', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  password: [
    { 
      validator: (rule, value, callback) => {
        if (!isEdit.value && !value) {
          callback(new Error('请输入密码'))
        } else {
          callback()
        }
      }, 
      trigger: 'blur' 
    }
  ]
}

const fetchUsers = async () => {
  loading.value = true
  try {
    const res = await request.get('/admin/users')
    userList.value = res.data || []
  } catch (error) {
    console.error('Fetch users failed:', error)
    ElMessage.error(error.msg || '获取账号列表失败')
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  isEdit.value = false
  form.value = {
    id: null,
    username: '',
    real_name: '',
    role: 'doctor',
    password: ''
  }
  dialogVisible.value = true
}

const openEditDialog = (row) => {
  isEdit.value = true
  form.value = { 
    id: row.id,
    username: row.username,
    real_name: row.real_name,
    role: row.role,
    password: '' // Don't show existing password
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        const payload = { ...form.value }
        if (isEdit.value && !payload.password) {
          delete payload.password // Don't send empty password on edit
        }
        
        if (isEdit.value) {
          await request.put(`/admin/users/${payload.id}`, payload)
          ElMessage.success('修改成功')
        } else {
          await request.post('/admin/users', payload)
          ElMessage.success('添加成功')
        }
        dialogVisible.value = false
        fetchUsers()
      } catch (error) {
        ElMessage.error(error.msg || '操作失败')
      } finally {
        submitting.value = false
      }
    }
  })
}

const handleDelete = (row) => {
  ElMessageBox.confirm(
    `确定要删除账号 ${row.real_name} (${row.username}) 吗？`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }
  ).then(async () => {
    try {
      await request.delete(`/admin/users/${row.id}`)
      ElMessage.success('已删除')
      fetchUsers()
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

onMounted(() => {
  fetchUsers()
})
</script>

<style scoped>
.user-management {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
