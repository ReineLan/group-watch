<script setup>
defineProps({title:String,eyebrow:String,desc:String,titleId:String})
</script>
<template>
  <header class="page-heading">
    <div class="page-heading-copy">
      <span v-if="eyebrow" class="eyebrow">{{eyebrow}}</span>
      <h1 :id="titleId">{{title}}<span>。</span></h1>
      <p v-if="desc" class="page-desc">{{desc}}</p>
    </div>
    <div v-if="$slots.default" class="page-heading-actions"><slot/></div>
  </header>
</template>
