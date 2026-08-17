package com.collector.pdd.data

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

object OutboxPayload {
    fun product(product: ProductEntity, platformCode: String): JSONObject {
        val urls = JSONArray()
        val files = JSONArray()
        product.mainImages.split("|").map { it.trim() }.filter { it.isNotEmpty() }.forEach { value ->
            when {
                value.startsWith("http://") || value.startsWith("https://") -> urls.put(value)
                value.startsWith("file://") && files.length() < 12 -> files.put(value.removePrefix("file://"))
                (File(value).exists() || value.startsWith("/")) && files.length() < 12 -> files.put(value)
            }
        }
        return JSONObject()
            .put("platform_code", platformCode)
            .put("keyword", product.keyword)
            .put("item_id", product.itemId)
            .put("sell_name", product.sellName)
            .put("product_name", product.productName)
            .put("brand", product.brand)
            .put("shop_name", product.shopName)
            .put("shop_id", product.shopId)
            .put("spec", product.spec)
            .put("sku_prices_text", product.skuPricesText)
            .put("sku_prices", product.skuPrices)
            .put("dosage_form", product.dosageForm)
            .put("approval_no", product.approvalNo)
            .put("manufacturer", product.manufacturer)
            .put("expiry", product.expiry)
            .put("category", product.category)
            .put("coupon_info", product.couponInfo)
            .put("item_url", product.itemUrl)
            .put("pick_tag", product.pickTag)
            .put("spec_list", product.specList)
            .put("sales_num", product.salesNum ?: JSONObject.NULL)
            .put("shop_sales_num", product.shopSalesNum ?: JSONObject.NULL)
            .put("comment_num", product.commentNum)
            .put("price", product.price ?: JSONObject.NULL)
            .put("display_price", product.displayPrice ?: JSONObject.NULL)
            .put("group_price", product.groupPrice ?: JSONObject.NULL)
            .put("deal_price", product.dealPrice ?: JSONObject.NULL)
            .put("original_price", product.originalPrice ?: JSONObject.NULL)
            .put("image_urls", urls)
            .put("local_image_paths", files)
            .put("local_image_count", files.length())
            .put("parse_status", product.parseStatus)
            .put("page_status", product.pageStatus)
            .put("quality_status", product.qualityStatus)
            .put("field_sources", JSONObject(product.fieldSources))
            .put("parser_version", product.parserVersion)
            .put("quality_rules_version", product.qualityRulesVersion)
    }

    fun localImageCount(payload: JSONObject): Int = payload.optJSONArray("local_image_paths")?.length() ?: 0
}
