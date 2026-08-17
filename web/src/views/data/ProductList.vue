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
        <el-button v-if="store.hasPerm('data:export')" @click="exportSelected">导出选中</el-button>
      </div>
      <el-alert v-if="displayError" :title="displayError" type="error" show-icon :closable="false" style="margin-bottom:12px">
        <template #default><el-button link type="primary" @click="load">重试</el-button></template>
      </el-alert>
      <el-table v-loading="loading" :data="list" stripe border @selection-change="(rows) => (selected = rows)">
        <template #empty><el-empty :description="loading ? '正在加载' : (error ? '商品列表加载失败' : '暂无商品')" /></template>
        <el-table-column type="selection" width="48" fixed />
        <el-table-column prop="product_id" label="ID" width="70" fixed />
        <el-table-column label="平台" width="90">
          <template #default="{ row }">{{ platformName(row.platform_code) }}</template>
        </el-table-column>
        <el-table-column prop="item_id" label="商品ID" width="130" />
        <el-table-column prop="sell_name" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="brand" label="品牌" width="100" show-overflow-tooltip />
        <el-table-column prop="shop_name" label="店铺" width="120" show-overflow-tooltip />
        <el-table-column label="列表价" width="90">
          <template #default="{ row }">{{ fmtPrice(row.price) }}</template>
        </el-table-column>
        <el-table-column label="详情价" width="90">
          <template #default="{ row }">{{ fmtPrice(row.display_price) }}</template>
        </el-table-column>
        <el-table-column label="拼单价" width="90">
          <template #default="{ row }">{{ fmtPrice(row.group_price) }}</template>
        </el-table-column>
        <el-table-column label="单独购买价" width="100">
          <template #default="{ row }">{{ fmtPrice(row.deal_price) }}</template>
        </el-table-column>
        <el-table-column label="销量" width="90">
          <template #default="{ row }">{{ row.sales_num ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="店铺销量" width="90">
          <template #default="{ row }">{{ row.shop_sales_num ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="规格" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.spec_text || row.spec || '-' }}</template>
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
        <el-table-column prop="approval_no" label="准字" width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="row.master_product_id" link type="success" @click="$router.push(`/products/${row.master_product_id}/timeline`)">时间线</el-button>
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
          <el-descriptions-item label="标题">{{ detail.sell_name || detail.product_name }}</el-descriptions-item>
          <el-descriptions-item label="商品ID">{{ detail.item_id }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ platformName(detail.platform_code) }}</el-descriptions-item>
          <el-descriptions-item label="品牌">{{ detail.brand || '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺">{{ detail.shop_name }}</el-descriptions-item>
          <el-descriptions-item label="准字">{{ detail.approval_no }}</el-descriptions-item>
          <el-descriptions-item label="规格">{{ detail.spec_text || detail.spec || '-' }}</el-descriptions-item>
          <el-descriptions-item label="列表价">{{ fmtPrice(detail.price) }}</el-descriptions-item>
          <el-descriptions-item label="详情价">{{ fmtPrice(detail.display_price) }}</el-descriptions-item>
          <el-descriptions-item label="拼单价">{{ fmtPrice(detail.group_price) }}</el-descriptions-item>
          <el-descriptions-item label="单独购买价">{{ fmtPrice(detail.deal_price) }}</el-descriptions-item>
          <el-descriptions-item label="销量">{{ detail.sales_num ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺销量">{{ detail.shop_sales_num ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="厂家">{{ detail.manufacturer }}</el-descriptions-item>
          <el-descriptions-item label="链接" :span="2"><a :href="detail.item_url" target="_blank">{{ detail.item_url }}</a></el-descriptions-item>
        </el-descriptions>
        <div class="sku-table-wrap">
          <div class="gallery-title">多规格售价（一行一个售卖规格）</div>
          <el-table v-if="skuRows(detail).length" :data="skuRows(detail)" size="small" border stripe>
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="spec" label="售卖规格" min-width="280" show-overflow-tooltip />
            <el-table-column label="售价" width="120">
              <template #default="{ row }">
                {{ row.normal_price != null && row.normal_price !== '' ? `¥${row.normal_price}` : '-' }}
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
        <el-form-item label="商品名称"><el-input v-model="editForm.product_name" /></el-form-item>
        <el-form-item label="品名/标题"><el-input v-model="editForm.sell_name" /></el-form-item>
        <el-form-item label="品牌"><el-input v-model="editForm.brand" /></el-form-item>
        <el-form-item label="规格"><el-input v-model="editForm.spec_text" /></el-form-item>
        <el-form-item label="批准文号"><el-input v-model="editForm.approval_no" /></el-form-item>
        <el-form-item label="生产厂家"><el-input v-model="editForm.manufacturer" /></el-form-item>
        <el-form-item label="列表价"><el-input-number v-model="editForm.price" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="单独购买价"><el-input-number v-model="editForm.deal_price" :min="0" :precision="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible=false">取消</el-button><el-button type="primary" @click="saveEdit">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { useUserStore } from '@/stores/user'

const store = useUserStore()
const platforms = ref([])
const list = ref([])
const selected = ref([])
const loading = ref(false)
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
const editForm = reactive({ product_id:null, product_name:'', sell_name:'', brand:'', spec_text:'', approval_no:'', manufacturer:'', price:null, deal_price:null })
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

function openGallery(row) {
  galleryUrls.value = imageUrls(row)
  if (!galleryUrls.value.length) {
    ElMessage.info('暂无图片')
    return
  }
  galleryVisible.value = true
}

async function load() {
  loading.value = true
  error.value = ''
  const params = new URLSearchParams()
  Object.entries(q).forEach(([k, v]) => { if (v) params.set(k, v) })
  params.set('page', String(page.value))
  params.set('limit', String(limit.value))
  try {
    const res = await http.get(`/api/products?${params}`)
    list.value = res.data?.items || []
    total.value = Number(res.data?.total || 0)
  } catch (e) {
    list.value = []
    total.value = 0
    error.value = e?.message || e?.detail || '商品列表加载失败'
  } finally {
    loading.value = false
  }
}
function applyFilters() { page.value = 1; load() }

async function openDetail(row) {
  const res = await http.get(`/api/products/${row.product_id}`)
  detail.value = res.data
  detailVisible.value = true
}

function openEdit(row) { Object.assign(editForm, row); editVisible.value = true }
async function saveEdit() { const id=editForm.product_id; const res=await http.put(`/api/products/${id}`, editForm); if(!res.ok)return; ElMessage.success('已保存'); editVisible.value=false; load() }
async function removeProduct(row) { await ElMessageBox.confirm(`确认删除商品 #${row.product_id}？`, '提示', {type:'warning'}); const res=await http.delete(`/api/products/${row.product_id}`); if(res.ok){ElMessage.success('已删除');load()} }

function exportSelected() {
  if (!selected.value.length) {
    ElMessage.warning('请先选择数据')
    return
  }
  const header = [
    'product_id', 'platform_code', 'item_id', 'sell_name', 'brand', 'shop_name',
    'price', 'display_price', 'group_price', 'deal_price',
    'sales_num', 'shop_sales_num', 'spec_text', 'sku_prices_text',
    'approval_no', 'item_url', 'image_count',
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
