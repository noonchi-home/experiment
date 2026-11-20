"""Deterministic Blender 4.2 household simulation; no existing photo editing.

Run: blender.exe --background --python tools/render_morning_3d.py -- --preview
All scene states and annotations are separate from the model observation JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "morning_3d_v1"
MATERIALS = {}
HUMAN = {}
OBJECTS = {}
COUNTER_MILK = Vector((0.64, 2.03, 1.16))
TABLE_MILK = Vector((0.43, -0.18, 0.98))
CUP_REST = Vector((-0.32, -0.16, 0.925))
JOINTS = ("hip", "chest", "neck", "head", "ls", "le", "lh", "rs", "re", "rh", "lk", "la", "rk", "ra")


def material(name, color):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.65
    MATERIALS[name] = result
    return result


def apply_material(obj, name):
    obj.data.materials.append(MATERIALS[name])
    return obj


def cube(name, location, size, mat, bevel=0.03):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name, obj.dimensions = name, size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    apply_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("rounded edges", "BEVEL")
        modifier.width, modifier.segments = bevel, 2
        obj.modifiers.new("weighted normals", "WEIGHTED_NORMAL")
    return obj


def sphere(name, location, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1, location=location)
    obj = bpy.context.object
    obj.name, obj.scale = name, scale
    apply_material(obj, mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def cylinder(name, location, radius, depth, mat, vertices=20):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    apply_material(obj, mat)
    obj.modifiers.new("weighted normals", "WEIGHTED_NORMAL")
    return obj


def bone(name, a, b, radius, mat):
    obj = cylinder(name, (0, 0, 0), radius, 1, mat, 12)
    set_bone(obj, a, b)
    return obj


def set_bone(obj, a, b):
    a, b = Vector(a), Vector(b)
    diff = b - a
    obj.location = (a + b) * 0.5
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = diff.to_track_quat("Z", "Y")
    obj.scale.z = diff.length


def parent_keep_world(obj, parent):
    matrix = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = matrix


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def create_scene(engine):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for name, color in {
        "wall": (0.81, 0.82, 0.80), "floor": (0.52, 0.34, 0.19),
        "wood": (0.66, 0.45, 0.23), "wood_dark": (0.31, 0.18, 0.08),
        "white": (0.93, 0.93, 0.90), "sheet": (0.62, 0.69, 0.74),
        "pillow": (0.85, 0.87, 0.88), "counter": (0.70, 0.72, 0.71),
        "metal": (0.45, 0.48, 0.50), "sink_dark": (0.13, 0.20, 0.23),
        "skin": (0.72, 0.45, 0.30), "shirt": (0.30, 0.38, 0.48),
        "pants": (0.055, 0.10, 0.18), "hair": (0.025, 0.020, 0.018),
        "blue": (0.03, 0.20, 0.79), "cup": (0.19, 0.58, 0.72),
        "food": (0.56, 0.24, 0.08), "fruit": (0.82, 0.16, 0.04),
        "green": (0.20, 0.39, 0.14), "door": (0.48, 0.55, 0.58),
    }.items():
        material(name, color)
    cube("wooden floor", (0, 0.1, -0.09), (7.0, 5.7, 0.18), "floor")
    for x in range(-6, 7):
        cube(f"floor seam {x}", (x * 0.5, 0.1, 0.005), (0.012, 5.65, 0.005), "wood_dark", 0)
    cube("back wall left", (-0.65, 2.72, 1.35), (5.2, 0.12, 2.7), "wall")
    cube("entry right jamb", (3.26, 2.72, 1.35), (0.22, 0.12, 2.7), "wall")
    cube("entry lintel", (2.64, 2.72, 2.45), (1.1, 0.12, 0.5), "wall")
    cube("left wall short", (-3.45, 1.1, 0.25), (0.12, 3.2, 0.5), "wall")
    # The front wall is omitted so fixed observer cameras can see inside.
    cube("bed frame", (-2.13, 1.02, 0.24), (1.42, 2.12, 0.35), "wood_dark")
    cube("mattress", (-2.13, 1.02, 0.48), (1.35, 2.06, 0.22), "white", .09)
    cube("gray bed cover", (-2.13, .72, .61), (1.32, 1.45, .09), "sheet", .07)
    cube("headboard", (-2.13, 2.12, .75), (1.48, .12, 1.15), "wood")
    sphere("pillow", (-2.13, 1.72, .66), (.48, .25, .10), "pillow")
    cube("bedside table", (-3.02, 1.73, .4), (.45, .45, .8), "wood")
    cylinder("lamp stand", (-3.02, 1.73, 1), .035, .35, "metal")
    cylinder("lamp shade", (-3.02, 1.73, 1.20), .17, .23, "white")
    cube("dining tabletop", (0, 0, .79), (1.45, .92, .10), "wood", .04)
    for x in (-.56, .56):
        for y in (-.32, .32):
            cube("table leg", (x, y, .38), (.08, .08, .76), "wood")
    cube("chair seat", (0, -.95, .44), (.52, .50, .09), "wood")
    cube("chair back", (0, -1.20, .78), (.52, .06, .70), "wood")
    for x in (-.21, .21):
        for y in (-1.15, -.75):
            cube("chair leg", (x, y, .22), (.06, .06, .44), "wood_dark")
    cube("kitchen cabinet", (1.05, 2.16, .46), (2.38, .76, .92), "white")
    cube("kitchen countertop", (1.05, 2.16, .96), (2.46, .82, .08), "counter")
    for x in (.15, .90, 1.65):
        cube("cabinet door seam", (x, 1.765, .46), (.012, .015, .85), "metal", 0)
        cube("cabinet handle", (x + .25, 1.74, .75), (.20, .025, .025), "metal")
    # Visible basin: inset dark volume and metallic raised rim, no flat icon.
    cube("sink basin", (1.70, 2.13, 1.014), (.67, .50, .025), "sink_dark", .07)
    for loc, size in [((1.70,1.86,1.04),(.77,.06,.06)),((1.70,2.40,1.04),(.77,.06,.06)),
                      ((1.30,2.13,1.04),(.06,.58,.06)),((2.10,2.13,1.04),(.06,.58,.06))]:
        cube("sink rim", loc, size, "metal", .02)
    bone("faucet upright", (1.9,2.42,1.04),(1.9,2.42,1.36),.025,"metal")
    bone("faucet spout", (1.9,2.42,1.36),(1.9,2.15,1.36),.025,"metal")
    cube("upper cupboard", (.95,2.55,1.95),(2.22,.30,.58),"white")
    cube("counter bread board", (.10,2.07,1.02),(.38,.30,.025),"wood")
    # Door pivot makes actual geometry rotate and occlude the person.
    bpy.ops.object.empty_add(location=(2.20,2.67,0))
    hinge=bpy.context.object; hinge.name="entry hinge"
    door=cube("entry door",(2.67,2.67,1.10),(.94,.08,2.20),"door")
    handle=cube("entry handle",(3.04,2.60,1.03),(.13,.04,.035),"metal")
    parent_keep_world(door,hinge);parent_keep_world(handle,hinge)
    OBJECTS['door']=hinge
    cube("outside corridor floor",(2.67,3.6,-.04),(1.4,2.0,.08),"counter")
    cube("corridor backdrop",(2.67,4.55,1.2),(1.5,.08,2.4),"wall")
    # Bottle has a recognizable shoulder, neck, and blue cap; never text labels.
    bpy.ops.object.empty_add(location=COUNTER_MILK)
    milk=bpy.context.object;milk.name="single milk bottle"
    for obj in [cylinder("milk body",COUNTER_MILK,.105,.27,"white"),
                cylinder("blue packaging band",COUNTER_MILK,.107,.075,"blue"),
                sphere("milk shoulder",COUNTER_MILK+Vector((0,0,.135)),(.105,.105,.07),"white"),
                cylinder("milk neck",COUNTER_MILK+Vector((0,0,.19)),.055,.07,"white"),
                cylinder("blue milk cap",COUNTER_MILK+Vector((0,0,.24)),.061,.045,"blue")]:
        parent_keep_world(obj,milk)
    # Product packaging text identifies the object; it is not a task/state label.
    bpy.ops.object.text_add(location=COUNTER_MILK+Vector((-.079,-.110,-.021)),rotation=(math.pi/2,0,0))
    label=bpy.context.object;label.name='milk packaging word';label.data.body='MILK'
    label.data.size=.055;label.data.extrude=.0005;apply_material(label,'white');parent_keep_world(label,milk)
    OBJECTS['milk']=milk
    bpy.ops.object.empty_add(location=CUP_REST)
    cup=bpy.context.object;cup.name="drinking cup"
    for obj in [cylinder("cup outer",CUP_REST,.087,.16,"cup"),
                cylinder("cup inside",CUP_REST+Vector((0,0,.083)),.073,.009,"sink_dark"),
                bone("cup handle top",CUP_REST+Vector((.08,0,.05)),CUP_REST+Vector((.14,0,.05)),.015,"cup"),
                bone("cup handle side",CUP_REST+Vector((.14,0,.05)),CUP_REST+Vector((.14,0,-.05)),.015,"cup"),
                bone("cup handle bottom",CUP_REST+Vector((.14,0,-.05)),CUP_REST+Vector((.08,0,-.05)),.015,"cup")]:
        parent_keep_world(obj,cup)
    liquid=cylinder("milk in cup",CUP_REST+Vector((0,0,.089)),.069,.004,"white")
    parent_keep_world(liquid,cup);OBJECTS['liquid']=liquid;OBJECTS['cup']=cup
    OBJECTS['plate']=cylinder("breakfast plate",(.02,.12,.856),.19,.025,"white")
    OBJECTS['toast']=cube("toast",(.02,.12,.895),(.21,.18,.04),"food",.025)
    OBJECTS['fruit']=sphere("small fruit",(-.14,.20,.91),(.055,.055,.055),"fruit")
    create_human()
    cameras=[]
    for name,position in [('left',(-5.5,-6.5,4.3)),('right',(5.4,-5.6,4.0))]:
        bpy.ops.object.camera_add(location=position)
        camera=bpy.context.object;camera.name=f"fixed {name} camera"
        camera.data.type='ORTHO';camera.data.ortho_scale=8.0
        look_at(camera,(0,.72,.83));cameras.append(camera)
    scene=bpy.context.scene
    scene.render.engine=engine
    scene.render.resolution_x=384;scene.render.resolution_y=288;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.render.film_transparent=False
    scene.world.color=(.75,.75,.75)
    scene.view_settings.view_transform='Standard'
    scene.display.shading.light='STUDIO';scene.display.shading.studiolight_rotate_z=.5
    scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True
    scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH'
    scene.display.shading.curvature_ridge_factor=1.3;scene.display.shading.curvature_valley_factor=1.1
    scene.display.shading.background_type='WORLD';scene.display.shading.show_specular_highlight=True
    scene.display.render_aa='8'
    if engine=='CYCLES':
        scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=True
    for name,location,power,size in [('window key',(-3,-2,5),900,5),('ceiling fill',(2,1,4),500,4)]:
        bpy.ops.object.light_add(type='AREA',location=location)
        light=bpy.context.object;light.name=name;light.data.energy=power;light.data.shape='DISK';light.data.size=size
        look_at(light,(0,1,0))
    return cameras


def create_human():
    for name,a,b,r,mat in [('torso','hip','chest',.20,'shirt'),('neck','chest','neck',.07,'skin'),
        ('left upper arm','ls','le',.060,'shirt'),('left forearm','le','lh',.044,'skin'),
        ('right upper arm','rs','re',.060,'shirt'),('right forearm','re','rh',.044,'skin'),
        ('left thigh','hip_l','lk',.082,'pants'),('left shin','lk','la',.067,'pants'),
        ('right thigh','hip_r','rk',.082,'pants'),('right shin','rk','ra',.067,'pants')]:
        HUMAN[name]=(bone(name,(0,0,0),(0,0,1),r,mat),a,b)
    for name,scale,mat in [('head',(.115,.12,.155),'skin'),('hair',(.121,.125,.09),'hair'),
        ('left hand',(.047,.045,.065),'skin'),('right hand',(.047,.045,.065),'skin'),
        ('left shoe',(.075,.14,.05),'pants'),('right shoe',(.075,.14,.05),'pants'),
        ('left eye',(.018,.014,.018),'hair'),('right eye',(.018,.014,.018),'hair'),
        ('nose',(.025,.035,.027),'skin')]:
        HUMAN[name]=sphere(name,(0,0,0),scale,mat)


def pose(root, yaw=0.0, sitting=0.0, lie=False, phase=0.0, walking=0.0):
    s=sitting;breath=.006*math.sin(phase*1.3)
    h=.96-.39*s; chest=1.35-.35*s+breath
    local={
        'hip':(0,0,h),'chest':(0,.015,chest),'neck':(0,.02,chest+.12),'head':(0,.025,chest+.29),
        'ls':(-.21,0,chest-.01),'rs':(.21,0,chest-.01),
        'le':(-.25,.03+.10*s,chest-.28),'re':(.25,.03+.10*s,chest-.28),
        'lh':(-.25,.06+.23*s,chest-.52+.06*s),'rh':(.25,.06+.23*s,chest-.52+.06*s),
        'hip_l':(-.11,0,h),'hip_r':(.11,0,h),
        'lk':(-.11,.31*s,.51-.02*s),'rk':(.11,.31*s,.51-.02*s),
        'la':(-.11,.33*s,.09),'ra':(.11,.33*s,.09),
    }
    stride=.12*walking*math.sin(phase*4.0)
    for name,sign in [('lk',1),('la',1),('rk',-1),('ra',-1)]:
        v=list(local[name]);v[1]+=stride*sign;local[name]=tuple(v)
    for name,sign in [('le',-1),('lh',-1),('re',1),('rh',1)]:
        v=list(local[name]);v[1]+=stride*.6*sign;local[name]=tuple(v)
    rotation=Matrix.Rotation(yaw,3,'Z')
    if lie:
        rotation=Matrix.Rotation(math.pi,3,'Z') @ Matrix.Rotation(math.pi/2,3,'X')
    result={key:Vector(root)+rotation@Vector(value) for key,value in local.items()}
    result['_rotation']=rotation
    return result


def mix_pose(a,b,factor):
    factor=max(0,min(1,factor));factor=factor*factor*(3-2*factor)
    result={key:a[key].lerp(b[key],factor) for key in a if key!='_rotation'}
    result['_rotation']=a['_rotation'].to_quaternion().slerp(b['_rotation'].to_quaternion(),factor).to_matrix()
    return result


def walk(path,fraction,phase):
    fraction=max(0,min(.999999,fraction))
    lengths=[(Vector(b)-Vector(a)).length for a,b in zip(path,path[1:])]
    distance=sum(lengths)*fraction
    for a,b,length in zip(path,path[1:],lengths):
        if distance<=length:
            direction=Vector(b)-Vector(a)
            position=Vector(a).lerp(Vector(b),distance/length)
            yaw=-math.atan2(direction.x,direction.y)
            return pose(position,yaw=yaw,phase=phase,walking=1)
        distance-=length
    return pose(path[-1],phase=phase)


def apply_human(p):
    rotation=p['_rotation']
    for value in HUMAN.values():
        if isinstance(value,tuple):
            obj,a,b=value;set_bone(obj,p[a],p[b])
    placements={'head':p['head'],'hair':p['head']+rotation@Vector((0,-.015,.095)),
        'left hand':p['lh'],'right hand':p['rh'],
        'left shoe':p['la']+rotation@Vector((0,.065,-.035)),
        'right shoe':p['ra']+rotation@Vector((0,.065,-.035)),
        'left eye':p['head']+rotation@Vector((-.042,.113,.025)),
        'right eye':p['head']+rotation@Vector((.042,.113,.025)),
        'nose':p['head']+rotation@Vector((0,.136,-.012))}
    for name,position in placements.items():
        obj=HUMAN[name];obj.location=position;obj.rotation_euler=rotation.to_euler()


def arm_to(p,side,target):
    shoulder=p['ls' if side=='left' else 'rs']
    hand='lh' if side=='left' else 'rh';elbow='le' if side=='left' else 're'
    p[hand]=Vector(target)
    p[elbow]=shoulder.lerp(Vector(target),.52)+Vector((-.08 if side=='left' else .08,-.07,-.05))


def set_visibility(human_visible):
    for value in HUMAN.values():
        obj=value[0] if isinstance(value,tuple) else value
        obj.hide_render=not human_visible


def state(sequence,t):
    milk=COUNTER_MILK.copy();cup=CUP_REST.copy();milk_rotation=Vector((0,0,0))
    door_angle=0.;visible=True;liquid=False;food=True
    lying=pose((-2.13,0,.72),lie=True,phase=t)
    bed_sit=pose((-1.35,.60,0),yaw=-math.pi/2,sitting=1,phase=t)
    bed_stand=pose((-1.35,.60,0),yaw=-math.pi/2,phase=t)
    seated=pose((0,-.97,0),sitting=1,phase=t)
    table_stand=pose((0,-.97,0),phase=t)
    kitchen=pose((.45,1.42,0),phase=t)
    activity=''
    if sequence=='training':
        if t<20:p=lying;activity='resting in bed'
        elif t<27:p=mix_pose(lying,bed_sit,(t-20)/6);activity='waking and sitting on bed edge'
        elif t<33:p=mix_pose(bed_sit,bed_stand,(t-27)/5);activity='standing from bed'
        elif t<57:
            p=walk([(-1.35,.60,0),(-1.35,-1.25,0),(0,-.97,0)],(t-33)/23,t);activity='walking to breakfast chair'
        elif t<63:p=mix_pose(table_stand,seated,(t-57)/5);activity='sitting at breakfast table without milk'
        elif t<78:p=seated;activity='seated at breakfast table without milk'
        elif t<83:p=mix_pose(seated,table_stand,(t-78)/4);activity='standing to fetch milk'
        elif t<90:
            p=walk([(0,-.97,0),(-.95,-.8,0),(-.95,1.4,0),(.45,1.42,0)],(t-83)/6,t);activity='walking to milk on counter'
        elif t<100:
            p=kitchen;f=(t-90)/9;arm_to(p,'right',p['rh'].lerp(COUNTER_MILK+Vector((0,-.04,0)),f));activity='reaching for and grasping milk bottle'
        elif t<115:
            p=walk([(.45,1.42,0),(-.95,1.4,0),(-.95,-.8,0),(0,-.97,0)],(t-100)/14,t)
            carrying=p['chest']+p['_rotation']@Vector((.23,.35,-.18));arm_to(p,'right',carrying)
            milk=p['rh']+Vector((0,.035,0));activity='carrying milk from counter toward breakfast seat'
        elif t<124:
            p=table_stand;hand_start=p['chest']+Vector((.23,.35,-.18))
            milk=hand_start.lerp(TABLE_MILK,(t-115)/8);arm_to(p,'right',milk+Vector((0,-.035,0)))
            activity='placing milk on tabletop next to breakfast seat'
        elif t<135:
            p=mix_pose(table_stand,seated,(t-124)/6);milk=TABLE_MILK.copy();activity='sitting beside supplied milk'
        elif t<150:
            p=seated;f=math.sin(math.pi*(t-135)/14);milk=TABLE_MILK.lerp(CUP_REST+Vector((.12,0,.27)),f)
            milk_rotation.y=-.95*f;arm_to(p,'right',milk+Vector((0,-.04,0)))
            liquid=t>=142;activity='pouring milk into cup and returning bottle to table'
        elif t<164:
            p=seated;milk=TABLE_MILK.copy();liquid=True;f=math.sin(math.pi*(t-150)/13)
            cup=CUP_REST.lerp(p['head']+Vector((0,.19,-.08)),f);arm_to(p,'left',cup+Vector((-.05,0,0)))
            activity='lifting cup to mouth and drinking milk'
        else:
            p=seated;milk=TABLE_MILK.copy();liquid=True
            arm_to(p,'left',Vector((-.20,-.15,.99+.04*math.sin(t*.7))))
            activity='eating breakfast with milk beside the seat'
    elif sequence=='wakeup':
        if t<=2:p=mix_pose(lying,bed_sit,t/4)
        elif t<=4:p=mix_pose(lying,bed_sit,t/4)
        elif t<=6:p=mix_pose(bed_sit,bed_stand,(t-4)/2)
        else:p=walk([(-1.35,.60,0),(-1.2,.25,0)],(t-6)/2,t)
        activity='new-day waking and getting out of bed'
    elif sequence in ('seated_without_milk','seated_with_milk'):
        p=mix_pose(table_stand,seated,min(1,t/5));activity='new-day sitting at breakfast table'
        if sequence=='seated_with_milk':milk=TABLE_MILK.copy()
    elif sequence=='cleanup':
        food=False;liquid=False;milk=Vector((.4,2.0,.3))
        if t<2:p=kitchen;arm_to(p,'right',Vector((.10,2.07,1.07)))
        elif t<5:p=walk([(.45,1.42,0),(2.67,1.90,0)],(t-2)/3,t)
        elif t<7:
            p=walk([(2.67,1.90,0),(2.67,3.4,0)],(t-5)/2,t);door_angle=-1.5
        else:p=pose((2.67,4,0),phase=t);visible=False;door_angle=-1.5*(8-t)
        activity='leaving empty cup and plate after partial clearing'
    else:raise ValueError(sequence)
    apply_human(p);set_visibility(visible)
    OBJECTS['milk'].location=milk;OBJECTS['milk'].rotation_euler=milk_rotation
    OBJECTS['cup'].location=cup;OBJECTS['liquid'].hide_render=not liquid
    OBJECTS['toast'].hide_render=not food;OBJECTS['fruit'].hide_render=not food
    OBJECTS['door'].rotation_euler.z=door_angle
    return {'second':t,'activity':activity,'person_visible':visible,
            'joint_positions':{k:list(v) for k,v in p.items() if k!='_rotation'},
            'milk_center':list(milk),'cup_center':list(cup),'door_angle':door_angle,
            'cup_contains_milk':liquid,'food_on_plate':food}


def file_hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def render_sequence(sequence,cameras,start,seconds,output):
    frames_dir=output/'camera_frames'/sequence;frames_dir.mkdir(parents=True,exist_ok=True)
    observations=[];states=[];hashes=[]
    scene=bpy.context.scene
    for t in seconds:
        record=state(sequence,t);states.append(record)
        paths={}
        for side,camera in zip(('left','right'),cameras):
            path=frames_dir/f'{t:04d}_{side}.png'
            scene.camera=camera;scene.render.filepath=str(path)
            bpy.ops.render.render(write_still=True)
            paths[side]=path.relative_to(output).as_posix()
            hashes.append({'second':t,'side':side,'path':paths[side],'sha256':file_hash(path)})
        observations.append({'timestamp':(start+timedelta(seconds=t)).isoformat(),
                             'left_image':paths['left'],'right_image':paths['right']})
        print(json.dumps({'sequence':sequence,'second':t,'completed_pair':True}),flush=True)
    (output/f'{sequence}_observations.json').write_text(json.dumps({'observations':observations},indent=2)+'\n',encoding='utf-8')
    metadata=output/'metadata';metadata.mkdir(exist_ok=True)
    (metadata/f'{sequence}_scene_states.json').write_text(json.dumps(states,indent=2)+'\n',encoding='utf-8')
    (metadata/f'{sequence}_asset_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    return len(observations)


def main():
    started_at=datetime.now().astimezone().isoformat();started_clock=time.perf_counter()
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--engine',choices=['BLENDER_WORKBENCH','CYCLES','BLENDER_EEVEE_NEXT'],default='BLENDER_WORKBENCH')
    parser.add_argument('--sequence',choices=['training','wakeup','seated_without_milk','seated_with_milk','cleanup','all'],default='all')
    parser.add_argument('--output',type=Path,default=DATA)
    args=parser.parse_args(argv);output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    cameras=create_scene(args.engine)
    if args.preview:
        preview=output/'preview';preview.mkdir(exist_ok=True)
        for sequence,t in [('training',98),('seated_with_milk',8),('wakeup',4)]:
            state(sequence,t)
            for side,camera in zip(('left','right'),cameras):
                bpy.context.scene.camera=camera;bpy.context.scene.render.filepath=str(preview/f'{sequence}_{t:03d}_{side}.png')
                bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(preview/'morning_scene.blend'))
        return
    names=['training','wakeup','seated_without_milk','seated_with_milk','cleanup'] if args.sequence=='all' else [args.sequence]
    counts={};sequence_seconds={}
    for name in names:
        day='2026-10-24' if name=='training' else '2026-10-25'
        clock={'training':'07:00:00','wakeup':'07:00:00','seated_without_milk':'07:02:00','seated_with_milk':'07:02:00','cleanup':'08:00:00'}[name]
        start=datetime.fromisoformat(f'{day}T{clock}+09:00')
        sequence_started=time.perf_counter()
        counts[name]=render_sequence(name,cameras,start,range(200 if name=='training' else 9),output)
        sequence_seconds[name]=round(time.perf_counter()-sequence_started,3)
    provenance={'kind':'procedural_3d_simulation','renderer':bpy.app.version_string,'engine':args.engine,
        'script_sha256':file_hash(Path(__file__)),'real_camera_capture':False,'synthetic':True,
        'camera_resolution':[384,288],'paired_resolution':[768,288],
        'camera_locations':{side:list(camera.location) for side,camera in zip(('left','right'),cameras)},
        'raw_cadence_hz':1,'training_raw_count':200,'training_span_seconds':199,
        'reflector_uniform_selection':'All 200 original temporal observations are selected; no padding or duplication.',
        'scope':'A short morning segment from a source day, not a complete 24-hour recording.',
        'truth_metadata_sent_to_model':False,'rendered_sequence_counts':counts,
        'started_at':started_at,'finished_at':datetime.now().astimezone().isoformat(),
        'elapsed_seconds':round(time.perf_counter()-started_clock,3),'sequence_elapsed_seconds':sequence_seconds,
        'renderer_source':'https://download.blender.org/release/Blender4.2/blender-4.2.0-windows-x64.zip',
        'camera_adaptation':'Two fixed virtual views reconstructed for this room; not the paper physical left-back/right-back camera calibration.',
        'visible_text':'Only MILK printed on the bottle packaging. No timestamps, state labels, expected actions, or captions.',
        'physical_motion':'Every timestamp recomputes articulated 3D scene geometry; still poses include small torso breathing.',
        'limitations':['Stylized procedural human, not a photorealistic person.','Scripted motion has no physics/contact solver.','The original paper does not specify this image resolution; it is an experimental choice.']}
    (output/'generation_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'morning_scene.blend'))


if __name__=='__main__':main()
