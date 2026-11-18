def balance(state):
    accepted=len(state['rows']);isolated=len(state['quarantine'])
    accounted=accepted+isolated+state['blank_count']+state['header_count']+state['duplicate_count']
    business=state.get('business',{})
    return {'input':state['input_count'],'accepted':accepted,'isolated':isolated,
        'blank':state['blank_count'],'headers':state['header_count'],'duplicates':state['duplicate_count'],
        'accounted':accounted,'balanced':accounted==state['input_count'],
        # 同口径：日汇直接沿用m5的分桶区间和，未观测缺口不压低上界，已观测交集不重复相加。
        'business':business,
        'partial_buckets':business.get('partial_buckets',0),
        # 记录守恒只说明行账平衡；存在未重新定界的缺口桶时，不得进入正式日汇。
        'finalized':business.get('finalized',False)}
