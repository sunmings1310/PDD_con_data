<template>
  <div class="product-page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="q.platform_code" clearable placeholder="平台" style="width:140px">
          <el-option v-for="p in platforms" :key="p.platform_code" :label="p.platform_name" :value="p.platform_code" />
        </el-select>
        <el-input v-model="q.keyword" placeholder="关键词" clearable style="width:160px" />
        <el-input v-model="q.brand" placeholder="品牌" clearable style="width:140px" />
        <el-input v-model="q.item_id" placeholder="商品ID" clearable style="width:160px" />
        <el-input v-model="q.approval_no" placeholder="批准文号" clearable style="width:160px" />
        <el-button type="primary" @click="applyFilters">查询</el-button>
        <el-button :loading="loading || refreshing" @click="load">{{ refreshing ? '正在刷新' : '刷新' }}</el-button>
        <el-button v-if="store.hasPerm('excel:match')" @click="$router.push('/products/excel-match')">Excel 批量查库/导出</el-button>
        <el-button v-if="store.hasPerm('data:export')" @click="exportSelected">导出选中</el-button>
      </div>
      <el-alert v-if="displayError" :title="displayError" type="error" show-icon :closable="false" style="margin-bottom:12px">
        <template #default><el-button link type="primary" @click="load">重试</el-button></template>
      </el-alert>
      <div v-if="refreshing" class="refreshing-hint">正在刷新，保留当前商品列表</div>
      <el-table v-loading="loading" :data="list" stripe border @selection-change="(rows) => (selected = rows)">
        <template #empty><el-empty v-if="loaded && !error" description="暂无商品" /></template>
        <el-table-column type="selection" width="48" fixed />
        <el-table-column prop="product_id" label="ID" width="70" fixed />
        <el-table-column label="平台" width="90">
          <template #default="{ row }">{{ platformName(row.platform_code) }}</template>
        </el-table-column>
        <el-table-column prop="platform_product_id" label="平台商品ID" width="130" />
        <el-table-column prop="platform_title" label="平台完整标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="brand" label="品牌" width="100" show-overflow-tooltip />
        <el-table-column prop="shop_name" label="店铺" width="120" show-overflow-tooltip />
        <el-table-column label="列表价" width="90">
          <template #default="{ row }">{{ fmtPrice(row.list_price) }}</template>
        </el-table-column>
        <el-table-column label="详情价" width="90">
          <template #default="{ row }">{{ fmtPrice(row.detail_price) }}</template>
        </el-table-column>
        <el-table-column label="拼单价" width="90">
          <template #default="{ row }">{{ fmtPrice(row.group_price) }}</template>
        </el-table-column>
        <el-table-column label="单独购买价" width="100">
          <template #default="{ row }">{{ fmtPrice(row.single_purchase_price) }}</template>
        </el-table-column>
        <el-table-column label="销量" width="90">
          <template #default="{ row }">{{ row.sales ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="店铺销量" width="90">
          <template #default="{ row }">{{ row.shop_sales ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="商品属性规格" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.product_attribute_spec || '-' }}</template>
        </el-table-column>
        <el-table-column label="图片附件" width="120">
          <template #default="{ row }">
            <div v-if="coverOf(row)" class="img-cell" @click.stop="openGallery(row)">
              <img class="thumb" :src="coverOf(row)" alt="封面" />
              <span class="img-count">{{ row.image_count || row.images?.length || 0 }}</span>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="approval_number" label="批准文号" width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="row.enterprise_product_id" link type="success" @click="$router.push(`/products/${row.enterprise_product_id}/timeline`)">时间线</el-button>
            <el-button v-if="isSuperAdmin" link type="warning" @click="openEdit(row)">修改</el-button>
            <el-button v-if="isSuperAdmin" link type="danger" @click="removeProduct(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="limit" :total="total"
        :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next"
        style="margin-top:16px;justify-content:flex-end" @change="load" />
    </div>

    <el-dialog v-model="detailVisible" title="商品详情" width="860px" destroy-on-close>
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="平台完整标题">{{ detail.stable_profile.platform_title || '-' }}</el-descriptions-item>
          <el-descriptions-item label="规范商品名称">{{ detail.stable_profile.canonical_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="平台商品ID">{{ detail.identity.platform_product_id }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ platformName(detail.identity.platform_code) }}</el-descriptions-item>
          <el-descriptions-item label="品牌">{{ detail.stable_profile.brand || '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺">{{ detail.latest_observation.shop_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="批准文号">{{ detail.stable_profile.approval_number || '-' }}</el-descriptions-item>
          <el-descriptions-item label="商品属性规格">{{ detail.stable_profile.product_attribute_spec || '-' }}</el-descriptions-item>
          <el-descriptions-item label="列表价">{{ fmtPrice(detail.latest_observation.list_price) }}</el-descriptions-item>
          <el-descriptions-item label="详情价">{{ fmtPrice(detail.latest_observation.detail_price) }}</el-descriptions-item>
          <el-descriptions-item label="拼单价">{{ fmtPrice(detail.latest_observation.group_price) }}</el-descriptions-item>
          <el-descriptions-item label="单独购买价">{{ fmtPrice(detail.latest_observation.single_purchase_price) }}</el-descriptions-item>
          <el-descriptions-item label="销量">{{ detail.latest_observation.sales ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺销量">{{ detail.latest_observation.shop_sales ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="生产厂家">{{ detail.stable_profile.manufacturer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="来源链接" :span="2"><a :href="detail.identity.source_url" target="_blank">{{ detail.identity.source_url }}</a></el-descriptions-item>
          <el-descriptions-item label="Provenance">{{ detail.provenance.status }}</el-descriptions-item>
        </el-descriptions>
        <div class="sku-table-wrap">
          <div class="gallery-title">多规格售价（一行一个售卖规格）</div>
          <el-table v-if="skuRows(detail).length" :data="skuRows(detail)" size="small" border stripe>
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="spec_text" label="SKU 购买组合" min-width="280" show-overflow-tooltip />
            <el-table-column label="售价" width="120">
              <template #default="{ row }">
                {{ skuPrice(row) != null ? `¥${skuPrice(row)}` : '-' }}
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="sku-empty">暂无多规格售价（需用新版 App 重新采集）</div>
        </div>
        <div class="detail-gallery">
          <div class="gallery-title">图片附件（{{ imageUrls(detail).length }}）— 点击可放大</div>
          <div class="gallery-grid">
            <el-image
              v-for="(url, idx) in imageUrls(detail)"
              :key="`${url}-${idx}`"
              :src="url"
              :preview-src-list="imageUrls(detail)"
              :initial-index="idx"
              fit="contain"
              preview-teleported
              hide-on-click-modal
              class="gallery-img"
            />
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="galleryVisible" title="图片附件" width="720px" destroy-on-close append-to-body>
      <div class="gallery-grid">
        <el-image
          v-for="(url, idx) in galleryUrls"
          :key="`${url}-${idx}`"
          :src="url"
          :preview-src-list="galleryUrls"
          :initial-index="idx"
          fit="contain"
          preview-teleported
          hide-on-click-modal
          class="gallery-img"
        />
      </div>
    </el-dialog>
    <el-dialog v-model="editVisible" title="超级管理员修改商品资料" width="680px">
      <el-form label-width="110px" :model="editForm">
        <el-form-item label="平台完整标题"><el-input v-model="editForm.platform_title" /></el-form-item>
        <el-form-item label="规范商品名称"><el-input v-model="editForm.canonical_name" /></el-form-item>
        <el-form-item label="品牌"><el-input v-model="editForm.brand" /></el-form-item>
        <el-form-item label="商品属性规格"><el-input v-model="editForm.product_attribute_spec" /></el-form-item>
        <el-form-item label="批准文号"><el-input v-model="editForm.approval_number" /></el-form-item>
        <el-form-item label="生产厂家"><el-input v-model="editForm.manufacturer" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible=false">取消</el-button><el-button type="primary" @click="saveEdit">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'
import { createRequestGeneration } from '@/utils/requestGeneration'
import { viewScope } from '@/utils/taskStatus'

const store = useUserStore()
const platforms = ref([])
const list = ref([])
const selected = ref([])
const loading = ref(false)
const refreshing = ref(false)
const loaded = ref(false)
const error = ref('')
const platformError = ref('')
const displayError = computed(() => error.value || platformError.value)
const page = ref(1)
const limit = ref(20)
const total = ref(0)
const detailVisible = ref(false)
const detail = ref(null)
const galleryVisible = ref(false)
const galleryUrls = ref([])
const editVisible = ref(false)
const editForm = reactive({ product_id:null, scope:'library', platform_title:'', canonical_name:'', brand:'', product_attribute_spec:'', approval_number:'', manufacturer:'', dosage_form:'', category:'', expiry:'' })
const isSuperAdmin = computed(() => store.profile?.role_code === 'super_admin')
const q = reactive({ platform_code: '', keyword: '', brand: '', item_id: '', approval_no: '' })

const PLATFORM_LABELS = {
  pinduoduo: '拼多多',
  tmall: '天猫',
  jd: '京东',
  douyin: '抖音',
}

function platformName(code) {
  if (!code) return '-'
  const hit = platforms.value.find((p) => p.platform_code === code)
  if (hit?.platform_name) return hit.platform_name
  return PLATFORM_LABELS[code] || code
}

function fmtPrice(v) {
  if (v === null || v === undefined || v === '') return '-'
  return v
}

function absUrl(u) {
  if (!u) return ''
  if (/^https?:\/\//i.test(u)) return u
  return u.startsWith('/') ? u : `/${u}`
}

function imageUrls(row) {
  if (Array.isArray(row?.media)) return row.media.map((i) => absUrl(i.url)).filter(Boolean)
  const imgs = row?.images || []
  if (imgs.length) {
    return imgs.map((i) => absUrl(i.url || i)).filter(Boolean)
  }
  if (row?.cover_url) return [absUrl(row.cover_url)]
  return []
}

function coverOf(row) {
  return absUrl(row.cover_url || row.images?.[0]?.url || '')
}

function skuRows(row) {
  if (Array.isArray(row?.sku?.sku_combinations)) return row.sku.sku_combinations
  const raw = row?.sku_prices_json || row?.sku_prices || ''
  if (raw) {
    try {
      const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(arr) && arr.length) {
        return arr.map((it) => ({
          spec: it.spec || it.name || '-',
          normal_price: it.normal_price ?? it.price ?? null,
        }))
      }
    } catch (_) { /* fallthrough */ }
  }
  const text = row?.sku_prices_text || ''
  if (!text) return []
  return text.split('|').map((p) => p.trim()).filter(Boolean).map((part) => {
    const m = part.match(/^(.+?)\(售价[¥￥]([\d.]+)\)$/)
    return { spec: m?.[1]?.trim() || part, normal_price: m?.[2] ? Number(m[2]) : null }
  })
}

function skuPrice(row) {
  return row.single_purchase_price ?? row.detail_price ?? row.group_price ?? row.list_price ?? row.original_price ?? null
}

function openGallery(row) {
  galleryUrls.value = imageUrls(row)
  if (!galleryUrls.value.length) {
    ElMessage.info('暂无图片')
    return
  }
  galleryVisible.value = true
}

const requestGeneration = createRequestGeneration()
const scope = computed(() => viewScope(store.enterpriseId, store.workspaceId, page.value, limit.value, q.platform_code, q.keyword, q.brand, q.item_id, q.approval_no))
async function load() {
  const token = requestGeneration.next(scope.value)
  const initial = !loaded.value
  loading.value = initial
  refreshing.value = !initial
  error.value = ''
  const params = new URLSearchParams()
  Object.entries(q).forEach(([k, v]) => { if (v) params.set(k, v) })
  params.set('page', String(page.value)); params.set('limit', String(limit.value))
  try {
    const res = await http.get(`/api/products?${params}`)
    if (!requestGeneration.isCurrent(token, scope.value)) return
    list.value = res.data?.items || []; total.value = Number(res.data?.total || 0); loaded.value = true
  } catch (e) {
    if (!requestGeneration.isCurrent(token, scope.value)) return
    error.value = e?.message || e?.detail || '商品列表加载失败'
  } finally {
    if (requestGeneration.isCurrent(token, scope.value)) { loading.value = false; refreshing.value = false }
  }
}
function applyFilters() { page.value = 1; load() }
watch(() => viewScope(store.enterpriseId, store.workspaceId), () => { requestGeneration.reset(scope.value, () => { list.value=[]; total.value=0; loaded.value=false; error.value=''; loading.value=false; refreshing.value=false }); load() })

async function openDetail(row) {
  const res = await http.get(`/api/products/${row.product_id}`)
  detail.value = res.data
  detailVisible.value = true
}

async function openEdit(row) {
  const res = await http.get(`/api/products/${row.product_id}/edit?scope=library`)
  Object.assign(editForm, res.data)
  editVisible.value = true
}
async function saveEdit() {
  const { product_id, ...payload } = editForm
  const res = await http.put(`/api/products/${product_id}`, payload)
  if(!res.ok)return
  ElMessage.success('已保存'); editVisible.value=false; load()
}
async function removeProduct(row) { await ElMessageBox.confirm(`确认删除商品 #${row.product_id}？`, '提示', {type:'warning'}); const res=await http.delete(`/api/products/${row.product_id}`); if(res.ok){ElMessage.success('已删除');load()} }

function exportSelected() {
  if (!selected.value.length) {
    ElMessage.warning('请先选择数据')
    return
  }
  const header = [
    'product_id', 'platform_code', 'platform_product_id', 'platform_title', 'canonical_name', 'brand', 'shop_name',
    'list_price', 'detail_price', 'group_price', 'single_purchase_price',
    'sales', 'shop_sales', 'product_attribute_spec', 'sku_prices_text',
    'approval_number', 'item_url', 'image_count',
  ]
  const lines = [header.join(',')]
  selected.value.forEach((r) => {
    lines.push(header.map((h) => `"${String(r[h] ?? '').replaceAll('"', '""')}"`).join(','))
  })
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'products_export.csv'
  a.click()
}

onMounted(async () => {
  try {
    const p = await http.get('/api/platforms')
    platforms.value = p.data || []
  } catch (e) {
    platformError.value = e?.message || e?.detail || '平台列表加载失败，已继续加载商品'
  }
  load()
})
</script>

<style scoped>
.img-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #e5e6eb;
  display: block;
  background: #f5f6f7;
}
.img-count {
  color: #86909c;
  font-size: 12px;
}
.detail-gallery {
  margin-top: 16px;
}
.gallery-title {
  margin-bottom: 8px;
  color: #86909c;
  font-size: 13px;
}
.gallery-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.gallery-img {
  width: 140px;
  height: 140px;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  background: #f7f8fa;
  overflow: hidden;
}
.gallery-img :deep(.el-image__inner) {
  object-fit: contain;
}
.sku-table-wrap {
  margin-top: 14px;
}
.sku-empty {
  color: #86909c;
  font-size: 13px;
  padding: 8px 0;
}
</style>
