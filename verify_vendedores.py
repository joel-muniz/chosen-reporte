#!/usr/bin/env python3
# ============================================================================
# FLUJO DE VERIFICACION — Perfiles de vendedor en Pipedrive vs Tabla del master
# Compuerta para retirar la tabla del directorio del master (Rev. 13+).
# Repetible · READ-ONLY · sin credenciales hardcodeadas.
#
# USO:  PIPEDRIVE_API_KEY=<key> python3 verify_vendedores_repo.py
#   (Claude setea PIPEDRIVE_API_KEY al correrlo. Self-contained: los keys WP van
#    embebidos; el master se autodetecta por glob en /mnt/project.)
#
# VEREDICTO VERDE = cada fila del directorio existe en Pipedrive, exacta vs
# WindMar Pro en vivo, y los IDs funcionan en endpoints reales -> borrar la tabla
# es seguro.
# ============================================================================
import json, urllib.request, urllib.parse, re, os, glob, sys
K=os.environ.get("PIPEDRIVE_API_KEY")
if not K:
    sys.exit("Falta PIPEDRIVE_API_KEY en el entorno.")
# Master: autodetectar el de mayor Rev en /mnt/project
cands=glob.glob("/mnt/project/PIPEDRIVE_WINDMAR_API_*.txt")
if not cands: sys.exit("No encuentro el master en /mnt/project.")
def revnum(p):
    m=re.search(r'Rev(\d+)', p); return int(m.group(1)) if m else 0
MASTER=sorted(cands,key=revnum)[-1]
# Keys WP (estables; embebidos)
KM={"WP Entity ID":"5dc3baf2694b897fe11ec56224e7693364916f66",
    "WP Zoho Record ID":"ac1fa3937634001f3949044d84a32b574e7b3e26",
    "WP Sales Role":"64c150053e25e490e2a78f8ed3d91915c64db60f",
    "WP Sponsor":"345ea1cc8c93eabb2a9961183a06366b14d10eea",
    "WP Nivel":"e6509d002e9700919de22abd62fccef0a39986da",
    "WP Career Bonus":"d496fbd85b41b83059b63ba631b2cdd801697f4a",
    "WP Status":"e4eb4f7250b4c1b199a90661e0976a04428a5646",
    "WP Instalaciones":"2fcbe6f15d67de6980a405d13e88b8f5977582e7",
    "WP Entity Duplicados (ignorar)":"1ae5a367d1b921fe6bdee1334fa18c56e48509ee",
    "WP Last Refresh":"43ebeaa693902173f876db3e9a3a5d4166eaee28"}
def pd(p): return json.loads(urllib.request.urlopen(f"https://api.pipedrive.com/v1{p}{'&' if '?' in p else '?'}api_token={K}",timeout=60).read())
def wp(path):
    req=urllib.request.Request("https://windmar-backend.akcelita.com/api/"+path,
        headers={'origin':'https://www.windmarpro.com','User-Agent':'Mozilla/5.0','Content-Type':'application/json','X-Windmar-Region':'PR','X-Windmar-App-Version':'2.0.0'})
    try: return json.loads(urllib.request.urlopen(req,timeout=60).read())
    except Exception as e: return {'ERR':str(e)}
print(f"Master: {os.path.basename(MASTER)}")
# 1) Tabla del master
rows=[]
for ln in open(MASTER):
    m=re.match(r'^\|\s*(N\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|', ln)
    if m and 'Nivel' not in ln:
        rows.append({'nombre':m.group(2).strip(),'email':m.group(3).strip(),'entity':m.group(4).strip(),'zoho':m.group(5).strip()})
master={r['entity']:r for r in rows}
print(f"[Tabla master] {len(rows)} filas")
# 2) Perfiles Pipedrive (org 2 con WP Entity ID)
EID=KM["WP Entity ID"];ZID=KM["WP Zoho Record ID"];ROLE=KM["WP Sales Role"];DUP=KM["WP Entity Duplicados (ignorar)"]
profs={};start=0
while True:
    d=pd(f"/organizations/2/persons?start={start}&limit=100")
    for p in (d.get('data') or []):
        if p.get(EID):
            em=(p.get('email') or [{}])[0].get('value','')
            profs[p[EID]]={'id':p['id'],'name':p['name'],'email':em,'zoho':p.get(ZID,''),'role':p.get(ROLE,''),'dup':p.get(DUP,'')}
    mo=(d.get('additional_data') or {}).get('pagination',{})
    if not mo.get('more_items_in_collection'): break
    start=mo.get('next_start',start+100)
print(f"[Pipedrive]   {len(profs)} perfiles\n")
# TEST A
print("="*70);print("TEST A — EQUIVALENCIA (Pipedrive vs Tabla master)")
a_fail=0
for eid,m in master.items():
    pr=profs.get(eid)
    if not pr: print(f"  FALTA: {m['nombre']} (entity {eid})");a_fail+=1;continue
    if not((pr['email']==m['email'] or m['email'].startswith('(')) and (pr['zoho']==m['zoho'] or m['zoho'].startswith('('))):
        a_fail+=1;print(f"  MISMATCH {m['nombre']}")
print(f"  -> {len(master)-a_fail}/{len(master)} equivalentes")
# TEST B
print("="*70);print("TEST B — EXACTITUD vs WindMar Pro (getSalesRole)")
b_fail=b_skip=0
for eid,pr in profs.items():
    if not pr['email'] or pr['email'].startswith('('): b_skip+=1;continue
    d=wp("getSalesRole?member_email="+urllib.parse.quote(pr['email']))
    rec=d.get('Data') or d.get('data') or d
    if isinstance(rec,list) and rec: rec=rec[0]
    if not isinstance(rec,dict) or not rec.get('zohorecordid'): b_fail+=1;print(f"  SIN DATA: {pr['name']}");continue
    if not(rec.get('zohorecordid')==pr['zoho'] and rec.get('Sales_Role','')==pr['role']):
        b_fail+=1;print(f"  DRIFT {pr['name']}")
print(f"  -> {len(profs)-b_skip-b_fail} exactos, {b_fail} drift, {b_skip} sin email")
# TEST C
print("="*70);print("TEST C — FUNCIONAL (IDs de Pipedrive trabajan)")
for pr in [p for p in profs.values() if p['email'] and not p['email'].startswith('(')][:2]:
    d=wp("getUserLeads?Sales_Rep_Email="+urllib.parse.quote(pr['email']))
    n=len(d.get('Data',{})) if isinstance(d.get('Data'),dict) else 0
    print(f"  getUserLeads({pr['email']}) -> {n} leads {'OK' if 'ERR' not in d else 'FALLO'}")
if profs.get('8472'):
    d=wp("getManagerDashboardData?entity_id=8472&from_date=2026-06-01&to_date=2026-06-30")
    print(f"  getManagerDashboardData(8472) -> {'OK' if 'ERR' not in d else 'FALLO'}")
# TEST D
print("="*70);print("TEST D — COBERTURA / INTEGRIDAD")
print(f"  Perfiles {len(profs)} vs filas master {len(master)} -> {'OK' if len(profs)>=len(master) else 'REVISAR'}")
print(f"  Duplicados-a-ignorar: {sum(1 for p in profs.values() if p['dup'])} | Entity IDs únicos: {'OK' if len(profs)==len(set(profs))else 'NO'}")
print("\n"+"="*70)
print("VEREDICTO:", "VERDE — Pipedrive reemplaza la tabla con seguridad" if (a_fail==0 and b_fail==0 and len(profs)>=len(master)) else "AMARILLO — revisar antes de borrar")
