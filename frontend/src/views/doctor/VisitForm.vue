<template>
  <div class="visit-form-container">
    <el-page-header @back="goBack" content="电子病历与处方开立">
      <template #extra>
        <div class="patient-info-tag">
          <el-tag type="success" effect="dark">{{ patientName }} ({{ studentId }})</el-tag>
        </div>
      </template>
    </el-page-header>

    <div class="main-content">
      <div class="resizable-container">
        <!-- 左侧：电子病历 -->
        <div class="left-panel" :style="{ width: leftWidth + 'px' }">
          <el-card class="box-card">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: bold;">电子病历</span>
                <el-tooltip content="仅保留诊断字段，快速开方。其余病历信息可稍后在历史记录中补充。" placement="top">
                  <el-checkbox v-model="quickMode" label="快速接诊" style="color: #e6a23c; font-weight: bold;" />
                </el-tooltip>
              </div>
            </template>
            <el-form :model="visitForm" label-position="top">
              <div v-show="!quickMode">
                <el-form-item label="主诉">
                  <el-input v-model="visitForm.chief_complaint" type="textarea" :rows="2"></el-input>
                </el-form-item>
                <el-form-item label="现病史">
                  <el-input v-model="visitForm.present_illness" type="textarea" :rows="2" @input="onTemplateInput('present_illness')"></el-input>
                </el-form-item>
                <el-form-item label="既往史（过敏史）">
                  <el-input v-model="visitForm.past_history" type="textarea" :rows="2"></el-input>
                </el-form-item>
                <el-form-item label="体格检查">
                  <el-input v-model="visitForm.physical_exam" type="textarea" :rows="2" @input="onTemplateInput('physical_exam')"></el-input>
                </el-form-item>
              </div>
              <el-form-item label="诊断" class="asterisk-left el-form-item--label-top">
                <div style="width: 100%; display: flex; flex-direction: column; gap: 10px;">
                  <el-autocomplete
                    v-model="diagnosisSearch"
                    :fetch-suggestions="querySearchDiagnosisAsync"
                    placeholder="快速检索并添加诊断 (输入拼音或名称)"
                    @select="handleDiagnosisSelect"
                    style="width: 100%"
                    clearable
                  >
                    <template #default="{ item }">
                      <div class="diagnosis-item">
                        <span>{{ item.name }}</span>
                        <span class="diagnosis-code">{{ item.code }}</span>
                      </div>
                    </template>
                  </el-autocomplete>
                  <el-input 
                    v-model="visitForm.diagnosis" 
                    type="textarea" 
                    :rows="3" 
                    placeholder="可在此直接编辑或手动输入多条诊断"
                  ></el-input>
                </div>
              </el-form-item>
              <div v-show="!quickMode">
                <el-form-item label="医生留言/小贴士 (如：适量运动，戒烟戒酒)">
                  <el-input v-model="visitForm.doctor_advice" type="textarea" :rows="2" placeholder="给患者的自定义建议..." @input="onTemplateInput('doctor_advice')"></el-input>
                </el-form-item>
              </div>
            </el-form>
          </el-card>
        </div>

        <!-- 拖拽分隔条 -->
        <div class="resize-handle" @mousedown="startResize">
          <div class="resize-line"></div>
        </div>

        <!-- 右侧：开处方 -->
        <div class="right-panel">
          <el-card class="box-card" header="处方开立">
            <!-- 药品搜索 -->
            <div class="drug-search">
              <el-select
                v-model="selectedDrugId"
                filterable
                remote
                reserve-keyword
                placeholder="输入药品或项目名称搜索"
                :remote-method="searchDrugs"
                :loading="loadingDrugs"
                style="width: 100%"
                @change="handleDrugSelect"
              >
                <el-option
                  v-for="item in drugOptions"
                  :key="item.option_id"
                  :label="`${item.name} [${item.specification}] (${item.option_label}) - ¥${item.display_price.toFixed(2)}`"
                  :value="item.option_id"
                >
                  <span style="float: left">{{ item.name }}</span>
                  <span style="float: right; color: #8492a6; font-size: 13px">
                    {{ item.specification }} | {{ (item.type === 1 || item.type === 3) ? '库存: ' + item.stock + ' | ' : '' }}{{ item.option_label }}: ¥{{ item.display_price.toFixed(2) }}
                  </span>
                </el-option>
              </el-select>
            </div>

            <!-- 已选药品列表 -->
            <el-table :data="prescriptionItems" style="width: 100%; margin-top: 20px" border size="small">
              <el-table-column prop="name" label="药品名称" min-width="120" />
              <el-table-column prop="specification" label="规格" width="100" />
              <el-table-column label="零散用药" width="80">
                <template #default="scope">
                  <el-checkbox v-model="scope.row.is_scattered" v-if="scope.row.type === 1" @change="(val) => { if (val) scope.row.days = 2; else scope.row.days = 1; }" />
                  <span v-else style="color: #909399; font-size: 12px;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="用法/用量" min-width="180">
                <template #default="scope">
                  <div class="usage-inputs" v-if="scope.row.type === 1">
                    <el-select
                      v-model="scope.row.usage"
                      placeholder="用法"
                      size="small"
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in usageOptions" :key="item" :label="item" :value="item" />
                    </el-select>

                    <el-select
                      v-model="scope.row.dosage"
                      placeholder="用量"
                      size="small"
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in dosageOptionsWithBlank" :key="item" :label="item" :value="item" />
                    </el-select>

                    <el-select
                      v-model="scope.row.frequency"
                      placeholder="频次"
                      size="small"
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in frequencyOptions" :key="item" :label="item" :value="item" />
                    </el-select>

                    <el-select 
                      v-model="scope.row.timing" 
                      placeholder="时间" 
                      size="small" 
                      style="width: 80px"
                      allow-create
                      filterable
                      default-first-option
                    >
                      <el-option v-for="item in timingOptions" :key="item" :label="item" :value="item" />
                    </el-select>
                    </div>
                    <div v-else>
                      <span style="color: #909399; font-size: 12px;">诊疗项目 (无需填写用法)</span>
                    </div>
                  </template>
                </el-table-column>
              <el-table-column label="天数" width="80">
                <template #default="scope">
                  <el-select 
                    v-model="scope.row.days" 
                    placeholder="天数" 
                    size="small" 
                    style="width: 100%"
                    v-if="scope.row.type === 1"
                  >
                    <el-option v-for="day in 7" :key="day" :label="day + '天'" :value="day" />
                  </el-select>
                  <span v-else style="color: #909399; font-size: 12px;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="数量" width="120">
                <template #default="scope">
                  <el-input-number 
                    v-model="scope.row.quantity" 
                    :min="1" 
                    :max="(scope.row.type === 1 || scope.row.type === 3) ? (scope.row.maxStock > 0 ? scope.row.maxStock : 999) : 999" 
                    size="small" 
                    style="width: 100px"
                  />
                </template>
              </el-table-column>
              <el-table-column label="单价" width="80">
                <template #default="scope">
                  {{ scope.row.price.toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column label="金额" width="80">
                <template #default="scope">
                  {{ (Math.round(scope.row.price * scope.row.quantity * 100) / 100).toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="60">
                <template #default="scope">
                  <el-button type="danger" link @click="removeDrug(scope.$index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <!-- 静脉给药配伍区域 -->
            <div style="margin-top: 16px;">
              <el-checkbox v-model="intravenousMode" style="margin-bottom: 8px;">
                <span style="font-weight: bold;">静脉给药（勾选后独立配伍）</span>
              </el-checkbox>
              <div v-if="intravenousMode" style="border: 1px solid #e4e7ed; border-radius: 4px; padding: 12px; background: #fafbfc;">
                <div v-for="(group, gi) in compatGroups" :key="group.id" style="margin-bottom: 12px; border: 1px dashed #c0c4cc; border-radius: 4px; padding: 10px;">
                  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-weight: bold; color: #409EFF;">配伍 {{ gi + 1 }}</span>
                    <el-button type="danger" link size="small" @click="removeCompatGroup(gi)">删除配伍</el-button>
                  </div>
                  <div style="margin-bottom: 8px;">
                    <el-select
                      :model-value="null"
                      filterable
                      remote
                      reserve-keyword
                      placeholder="搜索药品添加到本配伍"
                      :remote-method="searchIvDrugs"
                      :loading="ivDrugSearchLoading"
                      style="width: 100%"
                      @change="(val) => { handleIvDrugSelect(gi, val); }"
                      @clear="selectedIvDrugId = null"
                    >
                      <el-option
                        v-for="item in ivDrugOptions"
                        :key="item.option_id"
                        :label="`${item.name} [${item.specification}] (${item.option_label}) - ¥${item.display_price.toFixed(2)}`"
                        :value="item.option_id"
                      />
                    </el-select>
                  </div>
                  <el-table :data="group.items" border size="small" v-if="group.items.length">
                    <el-table-column prop="name" label="药品名称" min-width="100" />
                    <el-table-column prop="specification" label="规格" width="100" />
                    <el-table-column label="数量" width="100">
                      <template #default="scope">
                        <el-input-number v-model="scope.row.quantity" :min="1" :max="999" size="small" style="width: 80px" />
                      </template>
                    </el-table-column>
                    <el-table-column label="用量数值" width="120">
                      <template #default="scope">
                        <el-input-number v-model="scope.row.infusion_dosage_value" :min="0.1" :precision="1" size="small" style="width: 100px" placeholder="如200" />
                      </template>
                    </el-table-column>
                    <el-table-column label="单位" width="80">
                      <template #default="scope">
                        <el-select v-model="scope.row.infusion_dosage_unit" size="small" style="width: 70px">
                          <el-option v-for="u in infusionUnitOptions" :key="u" :label="u" :value="u" />
                        </el-select>
                      </template>
                    </el-table-column>
                    <el-table-column label="给药方式" width="140">
                      <template #default="scope">
                        <el-select v-model="scope.row.infusion_method" size="small" style="width: 120px">
                          <el-option v-for="m in infusionMethodOptions" :key="m" :label="m" :value="m" />
                        </el-select>
                      </template>
                    </el-table-column>
                    <el-table-column prop="price" label="单价" width="70">
                      <template #default="scope">{{ scope.row.price.toFixed(2) }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="60">
                      <template #default="scope">
                        <el-button type="danger" link @click="removeIvItemFromGroup(gi, scope.$index)">删除</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                  <div v-if="!group.items.length" style="color: #909399; font-size: 13px; text-align: center; padding: 10px;">请在搜索框中搜索药品添加到本配伍</div>
                </div>
                <el-button type="primary" link @click="createCompatGroup">+ 创建配伍</el-button>
              </div>
            </div>

            <!-- 特殊计量与用法备注 -->
            <el-form-item label="特殊计量与用法备注" style="margin-top: 12px;">
              <el-input
                v-model="visitForm.special_note"
                type="textarea"
                :rows="2"
                placeholder="如有特殊配药要求请在此备注，护士将据此进行特殊配药（如：生理盐水250ml+头孢曲松2g 静滴）"
                maxlength="500"
                show-word-limit
              />
            </el-form-item>

            <!-- 费用结算 -->
            <div class="footer-action">
              <el-form inline>
                <el-form-item label="诊察费">
                  <el-input-number v-model="visitForm.consultation_fee" :min="0" :precision="2" :step="1" />
                </el-form-item>
                <el-form-item label="总金额">
                  <span class="total-amount">¥ {{ totalAmount.toFixed(2) }}</span>
                </el-form-item>
              </el-form>
              <div class="buttons">
                <el-button @click="resetForm">重置</el-button>
                <el-button type="warning" @click="parkVisit" :loading="parking">{{ parkedId ? '更新挂单' : '挂单' }}</el-button>
                <el-button type="primary" @click="openSubmitConfirm" :loading="submitting">提交处方</el-button>
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </div>

    <el-dialog v-model="confirmDialogVisible" title="确认提交处方" width="900px">
      <el-descriptions border :column="2" title="就诊信息">
        <el-descriptions-item label="患者">{{ patientName }} ({{ studentId }})</el-descriptions-item>
        <el-descriptions-item label="诊断">{{ visitForm.diagnosis || '-' }}</el-descriptions-item>
        <el-descriptions-item v-if="quickMode" label="提示" :span="2">
          <span style="color: #e6a23c;">快速接诊模式，其余病历信息可稍后在历史记录中补充</span>
        </el-descriptions-item>
        <el-descriptions-item v-if="!quickMode" label="主诉" :span="2">{{ visitForm.chief_complaint || '无' }}</el-descriptions-item>
        <el-descriptions-item v-if="!quickMode" label="现病史" :span="2">{{ visitForm.present_illness || '无' }}</el-descriptions-item>
        <el-descriptions-item v-if="!quickMode" label="既往史（过敏史）" :span="2">{{ visitForm.past_history || '无' }}</el-descriptions-item>
        <el-descriptions-item v-if="!quickMode" label="体格检查" :span="2">{{ visitForm.physical_exam || '无' }}</el-descriptions-item>
        <el-descriptions-item v-if="!quickMode" label="医生留言" :span="2">{{ visitForm.doctor_advice || '无' }}</el-descriptions-item>
        <el-descriptions-item v-if="visitForm.special_note" label="特殊计量与用法备注" :span="2">
          <span style="color: #e6a23c; font-weight: bold;">{{ visitForm.special_note }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <div style="margin-top: 20px;">
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 10px;">处方明细</div>
        <!-- 普通药品 -->
        <el-table :data="prescriptionItems" border stripe size="small" v-if="prescriptionItems.length">
          <el-table-column prop="name" label="药品名称" min-width="140" />
          <el-table-column prop="specification" label="规格" width="120" />
          <el-table-column label="用法" min-width="220">
            <template #default="scope">
              <span v-if="scope.row.type === 1">
                {{ scope.row.usage }} / {{ scope.row.dosage }} / {{ scope.row.frequency }} / {{ scope.row.timing }}
              </span>
              <span v-else style="color: #909399">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" />
          <el-table-column label="单价" width="90">
            <template #default="scope">¥ {{ scope.row.price.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="100">
            <template #default="scope">¥ {{ (Math.round(scope.row.price * scope.row.quantity * 100) / 100).toFixed(2) }}</template>
          </el-table-column>
        </el-table>
        <!-- 静脉给药配伍 -->
        <div v-if="intravenousMode && compatGroups.some(g => g.items.length)" style="margin-top: 12px;">
          <div style="font-weight: bold; margin-bottom: 6px; color: #409EFF;">静脉给药配伍</div>
          <div v-for="(group, gi) in compatGroups" :key="group.id" v-show="group.items.length" style="margin-bottom: 10px; border: 1px solid #d9ecff; border-radius: 4px; padding: 8px; background: #ecf5ff;">
            <div style="font-weight: bold; font-size: 13px; margin-bottom: 4px;">配伍 {{ gi + 1 }}</div>
            <el-table :data="group.items" border stripe size="small">
              <el-table-column prop="name" label="药品名称" min-width="140" />
              <el-table-column prop="specification" label="规格" width="120" />
              <el-table-column label="用量" min-width="120">
                <template #default="scope">
                  {{ scope.row.infusion_dosage_value }}{{ scope.row.infusion_dosage_unit }}
                </template>
              </el-table-column>
              <el-table-column prop="infusion_method" label="给药方式" width="120" />
              <el-table-column prop="quantity" label="数量" width="80" />
              <el-table-column label="单价" width="90">
                <template #default="scope">¥ {{ scope.row.price.toFixed(2) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>

      <div class="confirm-totals">
        <div class="confirm-total-line">
          <span>处方小计</span>
          <span>¥ {{ drugTotalAmount.toFixed(2) }}</span>
        </div>
        <div class="confirm-total-line">
          <span>诊察费</span>
          <span>¥ {{ visitForm.consultation_fee.toFixed(2) }}</span>
        </div>
        <div class="confirm-total-line confirm-total-final">
          <span>应收总额</span>
          <span>¥ {{ totalAmount.toFixed(2) }}</span>
        </div>
      </div>

      <template #footer>
        <el-button @click="confirmDialogVisible = false" :disabled="submitting">取消</el-button>
        <el-button type="primary" @click="confirmSubmit" :loading="submitting">确认提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="templateDialogVisible" :title="templateDialogTitle" width="800px">
      <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
        <el-input v-model="templateKeyword" placeholder="搜索模板标题/内容" clearable @keyup.enter="loadTemplates" />
        <el-button @click="loadTemplates" :loading="templateLoading">查询</el-button>
      </div>
      <el-table :data="templateList" border stripe size="small" v-loading="templateLoading" @row-click="applyTemplate">
        <el-table-column prop="title" label="标题" width="220" />
        <el-table-column label="内容">
          <template #default="scope">
            <div style="white-space: pre-wrap; word-break: break-word; max-height: 160px; overflow: hidden;">
              {{ scope.row.content }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="170" />
      </el-table>
      <template #footer>
        <el-button @click="templateDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const patientId = route.query.patient_id
const patientName = route.query.patient_name
const studentId = route.query.student_id
const sourceVisitId = route.query.source_visit_id
const parkedId = ref(route.query.parked_id ? Number(route.query.parked_id) : null)
const parking = ref(false)

const diagnosisSearch = ref('')

// 拖拽调节相关
const leftWidth = ref(parseInt(localStorage.getItem('visitFormLeftWidth') || '420'))
const isResizing = ref(false)
const MIN_LEFT_WIDTH = 280
const MAX_LEFT_WIDTH = 700

const startResize = (e) => {
  isResizing.value = true
  const startX = e.clientX
  const startWidth = leftWidth.value
  
  const onMouseMove = (moveEvent) => {
    const delta = moveEvent.clientX - startX
    const newWidth = startWidth + delta
    leftWidth.value = Math.max(MIN_LEFT_WIDTH, Math.min(MAX_LEFT_WIDTH, newWidth))
  }
  
  const onMouseUp = () => {
    isResizing.value = false
    localStorage.setItem('visitFormLeftWidth', leftWidth.value.toString())
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }
  
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// 快速接诊模式
const quickMode = ref(false)

// 电子病历表单
const visitForm = ref({
  chief_complaint: '',
  present_illness: '',
  past_history: '无',
  physical_exam: '',
  diagnosis: '',
  doctor_advice: '',
  special_note: '',
  consultation_fee: 8.00
})

// 药品相关
const loadingDrugs = ref(false)
const drugOptions = ref([])
const selectedDrugId = ref(null)
const prescriptionItems = ref([])

// 静脉给药模式
const intravenousMode = ref(false)
const ivItems = ref([])
const ivDrugOptions = ref([])
const selectedIvDrugId = ref(null)
const ivDrugSearchLoading = ref(false)

// 配伍列表 [{id:1, items:[]}, {id:2, items:[]}]
const compatGroups = ref([])
let nextCompatId = 1

const createCompatGroup = () => {
  compatGroups.value.push({ id: nextCompatId++, items: [] })
}
const removeCompatGroup = (idx) => {
  compatGroups.value.splice(idx, 1)
}
const removeIvItemFromGroup = (groupIdx, itemIdx) => {
  compatGroups.value[groupIdx].items.splice(itemIdx, 1)
}

// 预设选项数据
const usageOptions = ref(['--', '口服', '嚼服', '冲泡', '冲服', '舌下含服', '外用', '静脉注射', '静脉滴注', '肌肉注射', '皮下注射', '雾化吸入', '含服', '外敷', '滴眼', '滴耳', '滴鼻'])
const infusionMethodOptions = ref(['静脉滴注', '静脉推注', '静脉输液泵', '微量泵'])
const infusionUnitOptions = ref(['ml', 'g', 'mg', 'μg', 'U', 'IU'])
const buildDosageOptions = () => {
  const out = []
  const push = (v) => {
    if (!v) return
    if (!out.includes(v)) out.push(v)
  }

  const halfUnits = ['片', '粒', '袋', '包']
  halfUnits.forEach(u => push(`半${u}`))

  const countUnits = ['片', '粒', '袋', '包', '支', '瓶', '贴', '喷', '丸', '次', '滴']
  countUnits.forEach(u => {
    for (let i = 1; i <= 6; i++) push(`${i}${u}`)
  })

  ;['1ml', '2ml', '5ml', '10ml', '20ml', '50ml', '100ml'].forEach(push)
  ;['0.5g', '1g', '2g', '5g', '10g', '15g', '20g'].forEach(push)
  push('适量')
  return out
}

const dosageOptions = ref(buildDosageOptions())
const dosageOptionsWithBlank = computed(() => ['--', ...buildDosageOptions()])
const frequencyOptions = ref(['--', '每日1次', '每日2次', '每日3次', '每日4次', '每4小时1次', '每6小时1次', '每8小时1次', '每12小时1次', '必要时', '睡前'])
const timingOptions = ['--', '餐前', '餐后', '餐中', '空腹', '睡前']

// 提交状态
const submitting = ref(false)
const confirmDialogVisible = ref(false)

const templateDialogVisible = ref(false)
const templateLoading = ref(false)
const templateList = ref([])
const templateKeyword = ref('')
const templateFieldKey = ref('')

const templateDialogTitle = computed(() => {
  if (templateFieldKey.value === 'chief_complaint') return '选择主诉模板'
  if (templateFieldKey.value === 'physical_exam') return '选择体格检查模板'
  if (templateFieldKey.value === 'doctor_advice') return '选择医生贴士模板'
  return '选择模板'
})

const templateCategoryByField = {
  present_illness: 'present_illness',
  physical_exam: 'physical_exam',
  doctor_advice: 'doctor_advice'
}

const onTemplateInput = (fieldKey) => {
  if (templateDialogVisible.value) return
  const value = String(visitForm.value[fieldKey] || '')
  if (!value.endsWith('##')) return
  templateFieldKey.value = fieldKey
  templateKeyword.value = ''
  templateDialogVisible.value = true
  loadTemplates()
}

const loadTemplates = async () => {
  const category = templateCategoryByField[templateFieldKey.value]
  if (!category) return
  templateLoading.value = true
  try {
    const res = await request.get('/doctor/templates', {
      params: {
        category,
        q: templateKeyword.value.trim()
      }
    })
    templateList.value = res.data || []
  } catch (error) {
    ElMessage.error(error.msg || '加载模板失败')
  } finally {
    templateLoading.value = false
  }
}

const applyTemplate = (row) => {
  const fieldKey = templateFieldKey.value
  if (!fieldKey) return
  const content = String((row && row.content) || '')
  const value = String(visitForm.value[fieldKey] || '')
  const base = value.endsWith('##') ? value.slice(0, -2) : value
  const prefix = base && !base.endsWith('\n') ? `${base}\n` : base
  visitForm.value[fieldKey] = `${prefix}${content}`
  templateDialogVisible.value = false
}

const totalAmount = computed(() => {
  const drugTotal = prescriptionItems.value.reduce((sum, item) => {
    return sum + Math.round(item.price * item.quantity * 100) / 100
  }, 0)
  const ivTotal = compatGroups.value.reduce((sum, g) =>
    sum + g.items.reduce((gs, iv) => gs + Math.round(iv.price * iv.quantity * 100) / 100, 0), 0)
  return Math.round((drugTotal + ivTotal + visitForm.value.consultation_fee) * 100) / 100
})

const drugTotalAmount = computed(() => {
  const drugTotal = prescriptionItems.value.reduce((sum, item) => sum + Math.round(item.price * item.quantity * 100) / 100, 0)
  const ivTotal = compatGroups.value.reduce((sum, g) =>
    sum + g.items.reduce((gs, iv) => gs + Math.round(iv.price * iv.quantity * 100) / 100, 0), 0)
  return Math.round((drugTotal + ivTotal) * 100) / 100
})

const loadRejectedVisitAsDraft = async () => {
  if (!sourceVisitId) return
  try {
    const res = await request.get(`/doctor/visits/${sourceVisitId}`)
    const detail = res.data || {}

    visitForm.value.chief_complaint = detail.chief_complaint || ''
    visitForm.value.present_illness = detail.present_illness || ''
    visitForm.value.past_history = detail.past_history || '无'
    visitForm.value.physical_exam = detail.physical_exam || ''
    visitForm.value.diagnosis = detail.diagnosis || ''
    visitForm.value.doctor_advice = detail.doctor_advice || ''
    visitForm.value.special_note = detail.special_note || ''
    visitForm.value.consultation_fee = Number(detail.consultation_fee || 8)

    const draftItems = Array.isArray(detail.items) ? detail.items : []
    const normalItems = []
    const ivItems = {}
    draftItems.forEach((item, idx) => {
      const quantity = Number(item.quantity || 1)
      const totalAmount = Number(item.amount || 0)
      const unitPrice = Number(item.price_at_visit || (quantity > 0 ? totalAmount / quantity : 0))
      const row = {
        id: item.drug_id,
        option_id: `draft-${idx}-${item.drug_id}-${item.is_scattered ? 1 : 0}`,
        name: item.drug_name,
        type: Number(item.drug_type || 1),
        specification: item.specification,
        price: Number.isFinite(unitPrice) ? Math.round(unitPrice * 100) / 100 : 0,
        maxStock: 999,
        is_scattered: !!item.is_scattered,
        quantity: quantity > 0 ? quantity : 1,
        usage: item.usage || '',
        dosage: item.dosage || '',
        frequency: item.frequency || '',
        timing: item.timing || '',
        days: Number(item.days || 1) > 0 ? Number(item.days || 1) : 1,
        is_intravenous: !!item.is_intravenous,
        infusion_group: item.infusion_group || null,
        infusion_dosage_value: item.infusion_dosage_value ?? null,
        infusion_dosage_unit: item.infusion_dosage_unit || '',
        infusion_method: item.infusion_method || ''
      }
      if (item.is_intravenous) {
        const gid = item.infusion_group || 0
        if (!ivItems[gid]) ivItems[gid] = []
        ivItems[gid].push(row)
      } else {
        normalItems.push(row)
      }
    })
    prescriptionItems.value = normalItems
    if (Object.keys(ivItems).length > 0) {
      intravenousMode.value = true
      Object.keys(ivItems).forEach(gid => {
        compatGroups.value.push({ id: Number(gid) || (nextCompatId++), items: ivItems[gid] })
      })
    }

    ElMessage.success('已载入被驳回处方，可重新修改后提交')
  } catch (error) {
    ElMessage.error(error.msg || '载入历史处方失败')
  }
}

onMounted(async () => {
  if (!patientId) {
    ElMessage.error('未指定患者，请先搜索')
    await router.push('/doctor/patient')
    return
  }
  // Load default drugs
  await searchDrugs('')
  // 优先加载挂单草稿，其次才是驳回草稿
  if (parkedId.value) {
    const loaded = await loadParkedDraft(parkedId.value)
    if (loaded) return
  }
  await loadRejectedVisitAsDraft()
})

const loadParkedDraft = async (id) => {
  try {
    const res = await request.get(`/doctor/parked-visits/${id}`)
    const d = res.data || {}
    visitForm.value = {
      chief_complaint: d.chief_complaint || '',
      present_illness: d.present_illness || '',
      past_history: d.past_history || '无',
      physical_exam: d.physical_exam || '',
      diagnosis: d.diagnosis || '',
      doctor_advice: d.doctor_advice || '',
      special_note: d.special_note || '',
      consultation_fee: d.consultation_fee || 0
    }
    quickMode.value = !!d.quick_mode
    prescriptionItems.value = Array.isArray(d.items) ? d.items : []
    ElMessage.success('已恢复挂单草稿')
    return true
  } catch (error) {
    if (error && error.status === 410) {
      ElMessage.warning('该挂单已过期，已自动清理')
    } else {
      ElMessage.error((error && error.msg) || '加载挂单失败')
    }
    parkedId.value = null
    return false
  }
}

const parkVisit = async () => {
  if (intravenousMode.value && compatGroups.value.some(g => g.items.length > 0)) {
    ElMessage.warning('静脉配伍不支持挂单，请先关闭静脉给药或清空配伍')
    return
  }
  if (!patientId) {
    ElMessage.error('缺少患者信息')
    return
  }
  parking.value = true
  try {
    const payload = {
      patient_id: patientId,
      ...visitForm.value,
      quick_mode: quickMode.value,
      items: prescriptionItems.value
    }
    const res = await request.post('/doctor/parked-visits', payload)
    parkedId.value = res.data && res.data.parked_id
    ElMessage.success('已挂单，可随后继续接诊')
    router.push('/doctor/patient')
  } catch (error) {
    ElMessage.error((error && error.msg) || '挂单失败')
  } finally {
    parking.value = false
  }
}

const goBack = () => {
  router.push('/doctor/patient')
}

const querySearchDiagnosisAsync = async (queryString, cb) => {
  if (!queryString) {
    cb([])
    return
  }
  try {
    const res = await request.get('/doctor/diagnoses/search', {
      params: { keyword: queryString }
    })
    // Element Plus autocomplete expects 'value' field for the input text
    const results = res.data.map(item => ({
      ...item,
      value: item.name
    }))
    cb(results)
  } catch (error) {
    console.error(error)
    cb([])
  }
}

const handleDiagnosisSelect = (item) => {
  const selectedText = `${item.name} (${item.code})`
  if (!visitForm.value.diagnosis) {
    visitForm.value.diagnosis = selectedText
  } else {
    visitForm.value.diagnosis += `\n${selectedText}`
  }
  // Clear the search input after selecting
  diagnosisSearch.value = ''
}

const searchDrugs = async (query) => {
  loadingDrugs.value = true
  try {
    const res = await request.get('/doctor/drugs/search', {
      params: { keyword: query }
    })
    const options = []
    ;(res.data || []).forEach(d => {
      if (d.variant_type === 'retail') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: '零散',
          display_price: d.price,
          is_scattered: false,
          maxStock: d.stock
        })
        return
      }
      if (d.variant_type === 'pack') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: '整装',
          display_price: d.price,
          is_scattered: false,
          maxStock: d.stock
        })
        return
      }
      if (d.variant_type === 'service') {
        options.push({
          ...d,
          option_id: `${d.id}:variant`,
          option_label: '项目',
          display_price: d.price,
          is_scattered: false,
          maxStock: 999
        })
        return
      }
      if (d.variant_type === 'consumable') {
        options.push({
          ...d,
          option_id: `${d.id}:consumable`,
          option_label: '耗材',
          display_price: d.price,
          is_scattered: false,
          maxStock: d.stock
        })
        return
      }
      options.push({
        ...d,
        option_id: `${d.id}:whole`,
        option_label: '整装',
        display_price: d.price,
        is_scattered: false,
        maxStock: d.stock
      })
      if (d.has_scattered && d.scattered_price != null) {
        const conv = d.conversion_rate || 1
        options.push({
          ...d,
          option_id: `${d.id}:scattered`,
          option_label: '零散',
          display_price: d.scattered_price,
          is_scattered: true,
          maxStock: (d.stock || 0) * conv
        })
      }
    })
    drugOptions.value = options
  } catch (error) {
    console.error(error)
  } finally {
    loadingDrugs.value = false
  }
}

const handleDrugSelect = (val) => {
  const drug = drugOptions.value.find(item => item.option_id === val)
  if (drug) {
    // Check if already added
    if (prescriptionItems.value.find(item => item.option_id === drug.option_id)) {
      ElMessage.warning('该项目已添加')
    } else {
      prescriptionItems.value.push({
        id: drug.id,
        option_id: drug.option_id,
        name: drug.name,
        type: drug.type,
        specification: drug.specification,
        price: Math.round(drug.display_price * 100) / 100,
        maxStock: drug.maxStock,
        is_scattered: drug.is_scattered,
        quantity: 1,
        usage: drug.type === 1 ? '口服' : '',
        dosage: '',
        frequency: drug.type === 1 ? '每日3次' : '',
        timing: drug.type === 1 ? '餐后' : '',
        days: drug.is_scattered ? 2 : 1
      })
    }
  }
  selectedDrugId.value = null
}

const removeDrug = (index) => {
  prescriptionItems.value.splice(index, 1)
}

// 静脉给药：搜索药品
const searchIvDrugs = async (query) => {
  ivDrugSearchLoading.value = true
  try {
    const res = await request.get('/doctor/drugs/search', {
      params: { keyword: query }
    })
    const options = []
    ;(res.data || []).forEach(d => {
      if (d.variant_type === 'retail') {
        options.push({ ...d, option_id: `${d.id}:variant`, option_label: '零散', display_price: d.price, is_scattered: false, maxStock: d.stock })
        return
      }
      if (d.variant_type === 'pack') {
        options.push({ ...d, option_id: `${d.id}:variant`, option_label: '整装', display_price: d.price, is_scattered: false, maxStock: d.stock })
        return
      }
      if (d.variant_type === 'service' || d.variant_type === 'consumable') return
      options.push({ ...d, option_id: `${d.id}:whole`, option_label: '整装', display_price: d.price, is_scattered: false, maxStock: d.stock })
      if (d.has_scattered && d.scattered_price != null) {
        const conv = d.conversion_rate || 1
        options.push({ ...d, option_id: `${d.id}:scattered`, option_label: '零散', display_price: d.scattered_price, is_scattered: true, maxStock: (d.stock || 0) * conv })
      }
    })
    ivDrugOptions.value = options
  } catch (error) {
    console.error(error)
  } finally {
    ivDrugSearchLoading.value = false
  }
}

// 静脉给药：添加药品到指定配伍
const handleIvDrugSelect = (groupIdx, val) => {
  const drug = ivDrugOptions.value.find(item => item.option_id === val)
  if (!drug) return
  const group = compatGroups.value[groupIdx]
  if (group.items.find(item => item.option_id === drug.option_id)) {
    ElMessage.warning('该配伍中已存在此药品')
    return
  }
  group.items.push({
    id: drug.id,
    option_id: drug.option_id,
    name: drug.name,
    type: drug.type,
    specification: drug.specification,
    price: Math.round(drug.display_price * 100) / 100,
    maxStock: drug.maxStock,
    is_scattered: drug.is_scattered,
    quantity: 1,
    infusion_dosage_value: null,
    infusion_dosage_unit: 'ml',
    infusion_method: '静脉滴注'
  })
}

// 监听处方项目变化，自动计算零散药物数量
watch(
  prescriptionItems,
  (newItems) => {
    newItems.forEach(item => {
      if (item.type === 1 && item.is_scattered) {
        // 解析用量
        let dosageAmount = 0
        if (item.dosage.includes('半')) {
          dosageAmount = 0.5
        } else {
          const dosageMatch = item.dosage.match(/(\d+)([片粒袋包支瓶贴喷丸次滴])/)
          if (!dosageMatch) return
          dosageAmount = parseFloat(dosageMatch[1])
          if (!dosageAmount) return
        }
        
        // 解析频次
        let frequencyAmount = 1
        const frequencyMatch = item.frequency.match(/每日(\d+)次/)
        if (frequencyMatch) {
          frequencyAmount = parseFloat(frequencyMatch[1])
        } else if (item.frequency.includes('每4小时')) {
          frequencyAmount = 6
        } else if (item.frequency.includes('每6小时')) {
          frequencyAmount = 4
        } else if (item.frequency.includes('每8小时')) {
          frequencyAmount = 3
        } else if (item.frequency.includes('每12小时')) {
          frequencyAmount = 2
        }
        
        // 计算总数量
        const days = item.days || 1
        item.quantity = Math.round(dosageAmount * frequencyAmount * days)
      }
    })
  },
  { deep: true }
)

const resetForm = () => {
  visitForm.value = {
    chief_complaint: '',
    present_illness: '',
    past_history: '无',
    physical_exam: '',
    diagnosis: '',
    doctor_advice: '',
    special_note: '',
    consultation_fee: 8.00
  }
  prescriptionItems.value = []
}

const validatePrescription = () => {
  if (!visitForm.value.diagnosis || !String(visitForm.value.diagnosis).trim()) {
    ElMessage.warning('请填写诊断信息')
    return false
  }
  const hasNormal = Array.isArray(prescriptionItems.value) && prescriptionItems.value.length > 0
  const hasIv = intravenousMode.value && compatGroups.value.some(g => g.items.length > 0)
  if (!hasNormal && !hasIv) {
    ElMessage.warning('请至少添加一条处方明细')
    return false
  }
  for (let i = 0; i < prescriptionItems.value.length; i++) {
    const item = prescriptionItems.value[i]
    const qty = Number(item.quantity)
    if (!Number.isFinite(qty) || qty <= 0) {
      ElMessage.warning(`第${i + 1}行数量不合法`)
      return false
    }
    if (item.type === 1) {
      const f = ['usage', 'dosage', 'frequency', 'timing']
      const allBlank = f.every(k => !item[k] || item[k] === '--')
      if (allBlank) {
        ElMessage.warning(`第${i + 1}行请至少填写用法、用量、频次、时间中的一项`)
        return false
      }
    }
  }
  // 校验静脉给药配伍
  if (intravenousMode.value) {
    for (let gi = 0; gi < compatGroups.value.length; gi++) {
      const group = compatGroups.value[gi]
      if (!group.items.length) continue
      for (let ii = 0; ii < group.items.length; ii++) {
        const iv = group.items[ii]
        const qty = Number(iv.quantity)
        if (!Number.isFinite(qty) || qty <= 0) {
          ElMessage.warning(`配伍${gi + 1} 第${ii + 1}行数量不合法`)
          return false
        }
        if (iv.infusion_dosage_value == null || isNaN(Number(iv.infusion_dosage_value)) || Number(iv.infusion_dosage_value) <= 0) {
          ElMessage.warning(`配伍${gi + 1} 第${ii + 1}行请填写用量数值`)
          return false
        }
        if (!String(iv.infusion_dosage_unit || '').trim()) {
          ElMessage.warning(`配伍${gi + 1} 第${ii + 1}行请选择单位`)
          return false
        }
        if (!String(iv.infusion_method || '').trim()) {
          ElMessage.warning(`配伍${gi + 1} 第${ii + 1}行请选择给药方式`)
          return false
        }
      }
    }
  }
  return true
}

const openSubmitConfirm = () => {
  if (!validatePrescription()) return
  confirmDialogVisible.value = true
}

const confirmSubmit = async () => {
  if (!confirmDialogVisible.value) return
  if (!validatePrescription()) return
  submitting.value = true
  try {
    // 普通药品提交时，'--'转为空字符串
    const blankVal = (v) => (v === '--' ? '' : v)
    const normalItems = prescriptionItems.value.map(item => ({
      drug_id: item.id,
      quantity: item.quantity,
      usage: blankVal(item.usage),
      dosage: blankVal(item.dosage),
      frequency: blankVal(item.frequency),
      timing: blankVal(item.timing),
      days: item.days,
      is_scattered: item.is_scattered || false,
      is_intravenous: false
    }))
    const ivItemsPayload = []
    if (intravenousMode.value) {
      compatGroups.value.forEach(group => {
        group.items.forEach(item => {
          ivItemsPayload.push({
            drug_id: item.id,
            quantity: item.quantity,
            usage: '',
            dosage: '',
            frequency: '',
            timing: '',
            days: 1,
            is_scattered: item.is_scattered || false,
            is_intravenous: true,
            infusion_group: group.id,
            infusion_dosage_value: item.infusion_dosage_value,
            infusion_dosage_unit: item.infusion_dosage_unit,
            infusion_method: item.infusion_method
          })
        })
      })
    }
    const payload = {
      patient_id: patientId,
      ...visitForm.value,
      items: [...normalItems, ...ivItemsPayload]
    }
    if (parkedId.value) {
      payload.parked_id = parkedId.value
    }
    
    await request.post('/doctor/visits', payload)
    confirmDialogVisible.value = false
    ElMessage.success('处方提交成功')
    router.push('/doctor/history')
  } catch (error) {
    ElMessage.error(error.msg || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.visit-form-container {
  padding: 20px;
}
.main-content {
  margin-top: 20px;
}
.resizable-container {
  display: flex;
  gap: 0;
  height: calc(100vh - 160px);
  overflow: hidden;
}
.left-panel {
  flex-shrink: 0;
  overflow-y: auto;
  padding-right: 8px;
}
.right-panel {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  padding-left: 8px;
  min-width: 500px;
}
.resize-handle {
  width: 8px;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background-color 0.2s;
}
.resize-handle:hover {
  background-color: #e4e7ed;
}
.resize-handle:active {
  background-color: #409eff;
}
.resize-line {
  width: 2px;
  height: 40px;
  background-color: #dcdfe6;
  border-radius: 1px;
}
.resize-handle:hover .resize-line {
  background-color: #409eff;
}
.drug-search {
  margin-bottom: 10px;
}
.usage-inputs {
  display: flex;
  gap: 5px;
}
.footer-action {
  margin-top: 20px;
  border-top: 1px solid #ebeef5;
  padding-top: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.total-amount {
  font-size: 20px;
  color: #f56c6c;
  font-weight: bold;
}
.diagnosis-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.diagnosis-code {
  color: #999;
  font-size: 12px;
  margin-left: 10px;
}
.confirm-totals {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}
.confirm-total-line {
  width: 260px;
  display: flex;
  justify-content: space-between;
  font-size: 14px;
}
.confirm-total-final {
  font-size: 18px;
  font-weight: bold;
  color: #f56c6c;
}
</style>
