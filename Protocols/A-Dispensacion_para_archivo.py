import math
from opentrons.types import Point
from opentrons import protocol_api
import time
import os
from datetime import datetime

# metadata
metadata = {
    'protocolName': 'Station A - Sample dispensing',
    'author': 'Aitor Gastaminza & José Luis Villanueva & Alex Gasulla & Manuel Alba & Daniel Peñil & David Martínez',
    'source': 'HU Central de Asturias',
    'apiLevel': '2.5',
    'description': 'Protocol for sample dispensing'
}

'''
'technician': '$technician',
'date': '$date'
'''
 
################################################
# CHANGE THESE VARIABLES ONLY
################################################
NUM_SAMPLES             = 90    # Number of samples to be moved. (<= 90)
NUM_POOLS               = 1     # Number of iterations over the samples
VOLUME_SAMPLE           = 200   # Sample volume to be moved
PHOTOSENSITIVE          = False # True if it has photosensitive reagents
################################################


run_id                      = 'dispensacion_y_lisado_muestras'
recycle_tip                 = False # Do you want to recycle tips? It shoud only be set True for testing
air_gap_vol_sample          = 25
volume_mix                  = 500 # Volume used on mix
x_offset                    = [0,0]
extra_dispensal             = 1
num_cols                    = math.ceil(NUM_SAMPLES / 8) # Columns we are working on

pipette_allowed_capacity    = 900 # Volume allowed in the pipette of 1000µl


def run(ctx: protocol_api.ProtocolContext):
    STEP = 0
    STEPS = {  # Dictionary with STEP activation, description and times
        1: {'Execute': True,    'description': 'Transferir muestras al deepwell ('+str(VOLUME_SAMPLE)+' ul)'},
    }

    for s in STEPS:  # Create an empty wait_time
        if 'wait_time' not in STEPS[s]:
            STEPS[s]['wait_time'] = 0

    #Folder and file_path for log time
    if not ctx.is_simulating():
        folder_path = '/var/lib/jupyter/notebooks/'+run_id
        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)
        file_path = folder_path + '/Station_A_time_log.txt'

    # Define Reagents as objects with their properties
    class Reagent:
        def __init__(self, name, flow_rate_aspirate, flow_rate_dispense, delay):
            self.name               = name
            self.flow_rate_aspirate = flow_rate_aspirate
            self.flow_rate_dispense = flow_rate_dispense
            self.delay              = delay 

    class Reagent2:
        def __init__(self, name, flow_rate_aspirate, flow_rate_dispense,
                     reagent_reservoir_volume, delay, num_wells, tip_recycling = 'none'):
            self.name = name
            self.flow_rate_aspirate = flow_rate_aspirate
            self.flow_rate_dispense = flow_rate_dispense
            self.reagent_reservoir_volume = reagent_reservoir_volume
            self.delay = delay
            self.num_wells = num_wells
            self.col = 0
            self.vol_well = 0
            self.tip_recycling = tip_recycling
            self.vol_well_original = reagent_reservoir_volume / num_wells

    # Reagents and their characteristics
    Samples = Reagent(name                  = 'Samples',
                      flow_rate_aspirate    = 50,
                      flow_rate_dispense    = 100,
                      delay                 = 0
                      ) 

    Lysis = Reagent2(name                      = 'Lysis',
                     flow_rate_aspirate        = 50,
                     flow_rate_dispense        = 100,
                     reagent_reservoir_volume  = 48000,
                     num_wells                 = 1,
                     delay                     = 0
                     ) 

    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('VALORES DE VARIABLES')
    ctx.comment(' ')
    ctx.comment('Número de muestras: ' + str(NUM_SAMPLES)) 
    ctx.comment('Número de ciclos de recogida (pools): ' + str(NUM_POOLS)) 
    ctx.comment('Volumen de muestra a mover: ' + str(VOLUME_SAMPLE) + ' ul') 
    ctx.comment('Foto-sensible: ' + str(PHOTOSENSITIVE))  
    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('VOLÚMENES PARA ' + str(NUM_SAMPLES) + ' MUESTRAS')
    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment(' ')

    ##################
    # Custom functions
    def move_vol_multichannel(pipet, reagent, source, dest, vol, air_gap_vol, x_offset,
                       pickup_height, disp_height, blow_out, touch_tip):
        '''
        x_offset: list with two values. x_offset in source and x_offset in destination i.e. [-1,1]
        pickup_height: height from bottom where volume
        disp_height: dispense height; by default it's close to the top (z=-2), but in case it is needed it can be lowered
        blow_out, touch_tip: if True they will be done after dispensing
        '''
        # SOURCE
        s = source.bottom(pickup_height).move(Point(x = x_offset[0]))
        pipet.aspirate(vol, s, rate = reagent.flow_rate_aspirate)  # aspirate liquid
        if air_gap_vol != 0:  # If there is air_gap_vol, switch pipette to slow speed
            pipet.aspirate(air_gap_vol, source.top(z = -2),
                           rate = reagent.flow_rate_aspirate)  # air gap

        # GO TO DESTINATION
        drop = dest.top(z = disp_height).move(Point(x = x_offset[1]))
        pipet.dispense(vol + air_gap_vol, drop,
                       rate = reagent.flow_rate_dispense)  # dispense all

        ctx.delay(seconds = reagent.delay) # pause for x seconds depending on reagent

        if blow_out == True:
            pipet.blow_out(dest.top(z = -2))
        if touch_tip == True:
            pipet.touch_tip(speed = 20, v_offset = -10)
   
    def divide_destinations(l, n):
        # Divide the list of destinations in size n lists.
        for i in range(0, len(l), n):
            yield l[i:i + n]

    def custom_mix(pipet, reagent, location, vol, rounds, blow_out, mix_height,
    x_offset, source_height = 5, touch_tip = False):
        '''
        Function for mixing a given [vol] in the same [location] a x number of [rounds].
        blow_out: Blow out optional [True,False]
        x_offset = [source, destination]
        source_height: height from bottom to aspirate
        mix_height: height from bottom to dispense
        '''
        if mix_height <= 0:
            mix_height = 3

        pipet.aspirate(1, location = location.bottom(
                        z = source_height).move(Point(x = x_offset[0])), rate = reagent.flow_rate_aspirate)

        for _ in range(rounds):
            pipet.aspirate(vol, location = location.bottom(
                z = source_height).move(Point(x = x_offset[0])), rate = reagent.flow_rate_aspirate)
            pipet.dispense(vol, location = location.bottom(
                z = mix_height).move(Point(x = x_offset[1])), rate = reagent.flow_rate_dispense)

        pipet.dispense(1, location = location.bottom(
            z = mix_height).move(Point(x = x_offset[1])), rate = reagent.flow_rate_dispense)

        if blow_out == True:
            pipet.blow_out(location.top(z = -2))  # Blow out
        if touch_tip == True:
            pipet.touch_tip(speed = 20, v_offset = -10)

    def generate_source_table(source,source_extra):
        '''
        Concatenate the wells frome the different origin racks
        '''
        num_cols = math.ceil(NUM_SAMPLES / 9)
        s = []
        for i  in range(num_cols):
            if i < 5:
                s += source[0].columns()[i] + source[1].columns()[i]+source[2].columns()[i]
            else:
                s += source[3].columns()[i - 5] + source[4].columns()[i - 5]+source[5].columns()[i - 5]
           
        return s

    def distribute_custom(pipette, reagent, volume, src, dest, waste_pool, pickup_height, extra_dispensal, dest_x_offset, disp_height=0):
        # Custom distribute function that allows for blow_out in different location and adjustement of touch_tip
        pipette.aspirate((len(dest) * volume) +extra_dispensal
                         , src.bottom(pickup_height), rate = reagent.flow_rate_aspirate)
        pipette.move_to(src.top(z=5))
        pipette.aspirate(air_gap_vol_sample, rate = reagent.flow_rate_aspirate)  # air gap
        for d in dest:
            pipette.dispense(volume + air_gap_vol_sample, d.top(), rate = reagent.flow_rate_dispense)
            pipette.move_to(d.top(z=5))
            pipette.aspirate(air_gap_vol_sample, rate = reagent.flow_rate_dispense)  # air gap
        try:
            pipette.blow_out(waste_pool.wells()[0].bottom(pickup_height + 3))
        except:
            pipette.blow_out(waste_pool.top(pickup_height + 3))
        return (len(dest) * volume)

    def pick_up_tip(pip, tips):
        nonlocal tip_track
        #if not ctx.is_simulating():
        if recycle_tip:
            pip.pick_up_tip(tips[0].wells()[0])
        else:
            if tip_track['counts'][pip] >= tip_track['maxes'][pip]:
                for i in range(3):
                    ctx._hw_manager.hardware.set_lights(rails=False)
                    ctx._hw_manager.hardware.set_lights(button=(1, 0 ,0))
                    time.sleep(0.3)
                    ctx._hw_manager.hardware.set_lights(rails=True)
                    ctx._hw_manager.hardware.set_lights(button=(0, 0 ,1))
                    time.sleep(0.3)
                ctx._hw_manager.hardware.set_lights(button=(0, 1 ,0))
                ctx.pause('Cambiar ' + str(pip.max_volume) + ' µl tipracks antes del pulsar Resume.')
                pip.reset_tipracks()
                tip_track['counts'][pip] = 0
                tip_track['num_refills'][pip] += 1
            pip.pick_up_tip()

    def drop_tip(pip):
        if recycle_tip == True:
            pip.return_tip()
        else:
            pip.drop_tip(home_after = False)
        tip_track['counts'][pip] += 8 if '8-Channel' in str(pip) else 1

    def start_run():
        ctx.comment(' ')
        ctx.comment('###############################################')
        ctx.comment('Empezando protocolo')
        if PHOTOSENSITIVE == False:
            ctx._hw_manager.hardware.set_lights(button = True, rails =  True)
        else:
            ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
        now = datetime.now()
        # dd/mm/YY H:M:S
        start_time = now.strftime("%Y/%m/%d %H:%M:%S")
        return start_time

    def finish_run():
        ctx.comment('###############################################')
        ctx.comment('Protocolo finalizado')
        ctx.comment(' ')
        #Set light color to blue
        ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
        now = datetime.now()
        # dd/mm/YY H:M:S
        finish_time = now.strftime("%Y/%m/%d %H:%M:%S")
        if PHOTOSENSITIVE==False:
            for i in range(10):
                ctx._hw_manager.hardware.set_lights(button = False, rails =  False)
                time.sleep(0.3)
                ctx._hw_manager.hardware.set_lights(button = True, rails =  True)
                time.sleep(0.3)
        else:
            for i in range(10):
                ctx._hw_manager.hardware.set_lights(button = False, rails =  False)
                time.sleep(0.3)
                ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
                time.sleep(0.3)
        ctx._hw_manager.hardware.set_lights(button = True, rails =  False)

        ctx.comment('Puntas de  200 ul utilizadas: ' + str(tip_track['counts'][m300]) + ' (' + str(round(tip_track['counts'][m300] / 96, 2)) + ' caja(s))')
        ctx.comment('Puntas de 1000 ul utilizadas: ' + str(tip_track['counts'][p1000]) + ' (' + str(round(tip_track['counts'][p1000] / 96, 2)) + ' caja(s))')
        ctx.comment('###############################################')

        return finish_time

    def log_step_start():
        ctx.comment(' ')
        ctx.comment('###############################################')
        ctx.comment('PASO '+str(STEP)+': '+STEPS[STEP]['description'])
        ctx.comment('###############################################')
        ctx.comment(' ')
        return datetime.now()

    def log_step_end(start):
        end = datetime.now()
        time_taken = (end - start)
        STEPS[STEP]['Time:'] = str(time_taken)

        ctx.comment(' ')
        ctx.comment('Paso ' + str(STEP) + ': ' +STEPS[STEP]['description'] + ' hizo un tiempo de ' + str(time_taken))
        ctx.comment(' ')

    ####################################
    # load labware and modules
    ####################################
    if NUM_SAMPLES <= 45:
        rack_num = 3
        ctx.comment('Los racks a utilizar son: ' + str(rack_num))
    else:
        rack_num = 6
        ctx.comment('Los racks a utilizar son: ' + str(rack_num))

    source_racks = [ctx.load_labware('opentrons_15_tuberack_falcon_15ml_conical', slot,
        'Source Tube Rack with snapcap ' + str(i + 1)) for i, slot in enumerate(['7', '4', '1', '8','5','2'][:rack_num])
    ]

    source_racks_extra = ctx.load_labware('opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical', '9','Lysis Tube Rack')

    Lysis.reagent_reservoir = source_racks_extra.wells_by_name()['A3']


    ##################################
    # Destination plate
    dest_deepwell_plate = ctx.load_labware('nest_96_wellplate_2ml_deep', '6', 'NEST 96 Deepwell Plate 2mL')



    ####################################
    # Load tip_racks
    tips1000 = [ctx.load_labware('opentrons_96_filtertiprack_1000ul', slot, '1000µl filter tiprack')
         for slot in ['11']]

    tips300 = [ctx.load_labware('opentrons_96_filtertiprack_200ul', slot, '200µl filter tiprack')
        for slot in ['10']]

    ################################################################################
    # Setup sources and destinations
    sources_sample          = generate_source_table(source_racks,source_racks_extra)[0:NUM_SAMPLES]
    
    dests_deepwell          = dest_deepwell_plate.wells()[0:NUM_SAMPLES]

    p1000 = ctx.load_instrument('p1000_single_gen2', 'right', tip_racks = tips1000) # load P1000 pipette
    m300 = ctx.load_instrument('p300_multi_gen2', 'left', tip_racks = tips300) # load P1000 pipette

    tip_track = {
        'counts': {m300: 0, p1000: 0},
        'maxes': {m300: 96 * len(m300.tip_racks), p1000: 96 * len(p1000.tip_racks)}, #96 tips per tiprack * number or tipracks in the layout
        'num_refills' : {m300 : 0, p1000: 0}
        }

    # used tip counter and set maximum tips available

    start_run()
  

    ############################################################################
    # STEP 1: ADD SAMPLES TO DEEPWELL
    ############################################################################
    STEP += 1
    if STEPS[STEP]['Execute'] == True:
        start = log_step_start()

        for pool in range(NUM_POOLS):
            for s, d in zip(sources_sample, dests_deepwell):
                if not p1000.hw_pipette['has_tip']:
                    pick_up_tip(p1000, tips1000)

                move_vol_multichannel(p1000, reagent = Samples, source = s, dest = d,
                        vol = VOLUME_SAMPLE, air_gap_vol = air_gap_vol_sample, x_offset = x_offset,
                        pickup_height = 4, disp_height = -10, blow_out = True, touch_tip = False)
                p1000.air_gap(air_gap_vol_sample)

                drop_tip(p1000)

                #pausar
                if pool < NUM_POOLS - 1:
                  ctx.pause('Cambiar las muestras para el pooling y cambiar el tipRacks de 1000 µl antes del pulsar Resume.')

        log_step_end(start)
    

    # Export the time log to a tsv file
    if not ctx.is_simulating():
        with open(file_path, 'w') as f:
            f.write('STEP\texecution\tdescription\twait_time\texecution_time\n')
            for key in STEPS.keys():
                row = str(key)
                for key2 in STEPS[key].keys():
                    row += '\t' + format(STEPS[key][key2])
                f.write(row + '\n')
        f.close()

    ############################################################################
    finish_run()
