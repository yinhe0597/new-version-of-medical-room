<template>
  <el-button type="warning" :icon="Lock" @click="dialogVisible = true">
    修改密码
  </el-button>

  <el-dialog
    v-model="dialogVisible"
    title="修改密码"
    width="min(400px, calc(100vw - 32px))"
    append-to-body
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="原密码" prop="oldPassword">
        <el-input v-model="form.oldPassword" type="password" show-password autocomplete="current-password" />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input v-model="form.newPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="确认新密码" prop="confirmPassword">
        <el-input v-model="form.confirmPassword" type="password" show-password autocomplete="new-password" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitPasswordChange">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock } from '@element-plus/icons-vue'
import request from '@/api/request'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const validateNewPassword = (_rule, value, callback) => {
  if (value === form.oldPassword) {
    callback(new Error('新密码不能与原密码相同'))
    return
  }
  callback()
}

const validateConfirmation = (_rule, value, callback) => {
  if (value !== form.newPassword) {
    callback(new Error('两次输入的新密码不一致'))
    return
  }
  callback()
}

const rules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 12, message: '新密码长度不能少于12位', trigger: 'blur' },
    { validator: validateNewPassword, trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirmation, trigger: 'blur' }
  ]
}

const resetForm = () => {
  form.oldPassword = ''
  form.newPassword = ''
  form.confirmPassword = ''
  formRef.value?.clearValidate()
}

const submitPasswordChange = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const res = await request.post('/auth/change-password', {
      old_password: form.oldPassword,
      new_password: form.newPassword
    })
    ElMessage.success(`${res.msg || '密码修改成功'}，请重新登录`)
    dialogVisible.value = false
    userStore.logout()
    await router.replace('/login')
  } catch (error) {
    ElMessage.error(error.msg || '密码修改失败')
  } finally {
    submitting.value = false
  }
}
</script>
