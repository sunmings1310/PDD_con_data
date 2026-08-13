<template>
  <div class="page-card">
    <div class="toolbar" style="flex-wrap:wrap"><el-select v-model="platform" placeholder="平台" style="width:130px"><el-option label="拼多多" value="pinduoduo" /><el-option label="天猫" value="tmall" /></el-select><el-input v-model="filters.product_name" clearable placeholder="商品名称" style="width:150px" /><el-input v-model="filters.spec" clearable placeholder="规格" style="width:130px" /><el-input v-model="filters.manufacturer" clearable placeholder="生产厂家" style="width:160px" /><el-input v-model="filters.approval_no" clearable placeholder="批准文号" style="width:170px" /><el-input-number v-model="filters.min_price" :min="0" placeholder="最低价" style="width:125px" /><span>至</span><el-input-number v-model="filters.max_price" :min="0" placeholder="最高价" style="width:125px" /><el-input-number v-model="bucket" :min="1" :max="500" /><span>元/价格段</span><el-button type="primary" @click="load">分析</el-button><el-button @click="reset">重置</el-button></div>
    <el-row :gutter="12" style="margin:16px 0"><el-col :span="8"><el-statistic title="商品数" :value="data.summary?.product_count||0" /></el-col><el-col :span="8"><el-statistic title="总销量" :value="data.summary?.sales_total||0" /></el-col><el-col :span="8"><el-statistic title="均价" :value="data.summary?.avg_price||0" prefix="¥" /></el-col></el-row>
    <el-tabs>
      <el-tab-pane label="销量排行价格"><el-table :data="data.top_sales||[]" border><el-table-column prop="product_name" label="商品" /><el-table-column prop="spec_text" label="规格" /><el-table-column prop="effective_price" label="价格" /><el-table-column prop="sales_num" label="销量" /></el-table></el-tab-pane>
      <el-tab-pane label="最低价销量"><el-table :data="data.lowest_prices||[]" border><el-table-column prop="product_name" label="商品" /><el-table-column prop="effective_price" label="最低价" /><el-table-column prop="sales_num" label="销量" /></el-table></el-tab-pane>
      <el-tab-pane label="价格段"><el-table :data="data.price_segments||[]" border><el-table-column prop="range" label="价格段" /><el-table-column prop="product_count" label="商品数" /><el-table-column prop="sales_total" label="销量" /></el-table></el-tab-pane>
      <el-tab-pane label="热门规格"><el-table :data="data.popular_specs||[]" border><el-table-column prop="spec" label="规格" /><el-table-column prop="product_count" label="商品数" /><el-table-column prop="sales_total" label="销量" /></el-table></el-tab-pane>
      <el-tab-pane label="多盒装单盒价"><el-table :data="data.multi_box_unit_prices||[]" border><el-table-column prop="product_name" label="商品" /><el-table-column prop="spec" label="套餐" /><el-table-column prop="boxes" label="盒数" /><el-table-column prop="total_price" label="总价" /><el-table-column prop="unit_price" label="单盒价" /></el-table></el-tab-pane>
    </el-tabs>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'; import http from '@/api/http'
const platform=ref('pinduoduo'); const bucket=ref(20); const data=ref({})
const filters=reactive({product_name:'',spec:'',manufacturer:'',approval_no:'',min_price:null,max_price:null})
async function load(){const q=new URLSearchParams({bucket_size:String(bucket.value),platform_code:platform.value});Object.entries(filters).forEach(([k,v])=>{if(v!==''&&v!==null&&v!==undefined)q.set(k,String(v))});const res=await http.get(`/api/reports/overview?${q}`);data.value=res.data||{}}
function reset(){Object.assign(filters,{product_name:'',spec:'',manufacturer:'',approval_no:'',min_price:null,max_price:null});load()}
onMounted(load)
</script>
