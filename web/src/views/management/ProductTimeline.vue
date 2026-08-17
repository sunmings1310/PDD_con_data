<template>
  <div>
    <div class="page-card">
      <div class="toolbar"><el-button @click="$router.back()">返回</el-button><el-button type="primary" @click="load">刷新</el-button></div>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="load">重试</el-button></template></el-alert>
      <el-descriptions v-if="product" :column="3" border>
        <el-descriptions-item label="Product">#{{ product.master_product_id || route.params.id }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ product.platform_code || '-' }}</el-descriptions-item>
        <el-descriptions-item label="商品标识">{{ product.platform_product_id || '-' }}</el-descriptions-item>
      </el-descriptions>
    </div>
    <div class="page-card" v-loading="loading">
      <el-empty v-if="!loading && !error && !items.length" description="该商品暂无可查看的 Snapshot" />
      <el-timeline v-else>
        <el-timeline-item v-for="row in items" :key="row.snapshot_id" :timestamp="fmt(row.collected_at)" placement="top" :type="diffs(row).length ? 'warning' : 'success'">
          <el-card shadow="never">
            <template #header><div class="snapshot-head"><strong>Snapshot #{{ row.snapshot_id }}</strong><div><el-tag :type="qualityType(row.quality_status)">{{ row.quality_status || '-' }}</el-tag><el-tag v-for="d in diffs(row)" :key="d" class="diff-tag" type="warning">{{ diffLabel(d) }}</el-tag></div></div></template>
            <el-descriptions :column="4" border size="small">
              <el-descriptions-item label="价格">{{ money(row.price) }}</el-descriptions-item><el-descriptions-item label="销量">{{ row.sales_num ?? row.sales ?? '-' }}</el-descriptions-item><el-descriptions-item label="商品状态">{{ row.availability || row.product_status || '-' }}</el-descriptions-item><el-descriptions-item label="Parser">{{ row.parser_version || '-' }}</el-descriptions-item>
              <el-descriptions-item label="Task / Job / Attempt" :span="4"><el-link v-if="row.task_id" type="primary" @click="$router.push(`/tasks/${row.task_id}/trace`)">T#{{ row.task_id }}</el-link><span> / J#{{ row.job_id || '-' }} / A#{{ row.attempt_id || '-' }}</span></el-descriptions-item>
            </el-descriptions>
            <el-collapse v-if="sku(row) || changes(row)"><el-collapse-item title="SKU 与变化详情"><h4>SKU</h4><pre>{{ pretty(sku(row)) }}</pre><h4>Difference</h4><pre>{{ pretty(changes(row)) }}</pre></el-collapse-item></el-collapse>
          </el-card>
        </el-timeline-item>
      </el-timeline>
      <el-pagination class="pager" background layout="total, sizes, prev, pager, next" :total="total" :current-page="page" :page-size="limit" :page-sizes="[10,20,50]" @update:current-page="changePage" @update:page-size="changeLimit" />
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'; import { useRoute } from 'vue-router'; import dayjs from 'dayjs'; import http from '@/api/http'
const route=useRoute(),items=ref([]),product=ref(null),page=ref(1),limit=ref(20),total=ref(0),loading=ref(false),error=ref('')
function fmt(v){return v?dayjs(v).format('YYYY-MM-DD HH:mm:ss'):'-'} function money(v){return v===null||v===undefined||v===''?'-':`¥${v}`}
function parsed(v){if(!v)return null;if(typeof v!=='string')return v;try{return JSON.parse(v)}catch{return v}} function pretty(v){return v?JSON.stringify(parsed(v),null,2):'-'}
function sku(r){return r.sku_json||r.sku||r.normalized_json?.sku} function changes(r){return r.difference?.changes||r.diff?.changes||r.diff?.changed_fields||r.changed_fields||r.changed_fields_json}
function diffs(r){const d=r.difference||r.diff||{};const v=d.changed_fields||r.changed_fields||r.changed_fields_json;const x=parsed(v);if(Array.isArray(x))return x;if(x&&typeof x==='object')return Object.keys(x);return ['price_changed','sales_changed','sku_changed','availability_changed','title_changed','shop_changed'].filter(k=>d[k])}
function diffLabel(v){return ({price_changed:'价格变化',sales_changed:'销量变化',sku_changed:'SKU 变化',availability_changed:'状态变化',title_changed:'标题变化',shop_changed:'店铺变化'})[v]||v} function qualityType(v){return v==='passed'?'success':v==='warning'?'warning':'danger'}
async function load(){loading.value=true;error.value='';try{const res=await http.get(`/api/management/products/${route.params.id}/snapshots`,{params:{page:page.value,limit:limit.value}});items.value=res.data?.items||[];total.value=Number(res.data?.total||0);page.value=Number(res.data?.page||page.value);limit.value=Number(res.data?.limit||limit.value);product.value=res.data?.product||items.value[0]||product.value}catch(e){items.value=[];total.value=0;error.value=e.response?.data?.detail||e.message||'加载 Snapshot 时间线失败'}finally{loading.value=false}}
function changePage(v){page.value=v;load()}function changeLimit(v){limit.value=v;page.value=1;load()}onMounted(load)
</script>
<style scoped>.snapshot-head{display:flex;justify-content:space-between;gap:12px}.diff-tag{margin-left:6px}.pager{margin-top:16px;justify-content:flex-end}pre{white-space:pre-wrap;word-break:break-word;background:#f7f8fa;padding:10px}</style>
