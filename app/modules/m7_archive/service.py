from app.modules.m7_archive.export_out import checksum

def execute(state):
    finalized=state.get('reconcile',{}).get('finalized',False)
    state['archive']={'sha256':checksum(state),'evidence_count':len(state.get('calculations',[]))+len(state['quarantine']),
        # ready仅代表行账守恒可出证据；可正式归档还要求所有分桶完成交集回填并重新定界。
        'ready':state.get('reconcile',{}).get('balanced',False),'finalized':finalized,
        'partial_buckets':state.get('business',{}).get('partial_buckets',0)}
    return state
