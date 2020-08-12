import math
from opentrons.types import Point
from opentrons import protocol_api
import time
import os
import numpy as np
from timeit import default_timer as timer
import json
from datetime import datetime
import csv

# metadata
metadata = {
    'protocolName': 'Station C - Vitro',
    'author': 'Aitor Gastaminza & José Luis Villanueva & Alex Gasulla & Manuel Alba & Daniel Peñil & David Martínez',
    'source': 'Hospital Universitario Central de Asturias',
    'apiLevel': '2.5',
    'description': 'Protocol for sample setup (C) prior to qPCR (Vitro)'
    }

'''
'technician': '$technician',
'date': '$date'
'''

################################################
# CHANGE THESE VARIABLES ONLY
################################################
NUM_SAMPLES                 = 96    # Number of samples to be moved
VOLUME_PCR_SAMPLE           = 5     # Volume of the sample for PCR plate
VOLUME_ARCHIVE_SAMPLE       = 95    # Volume of the sample to file
PCR_PLATE_COL_OFFSET        = 0     # Number of PCR plate columns to skip dispensing samples
PAUSE_ON_PCR_READY          = True  # Pause when PCR plate is ready to go
PHOTOSENSITIVE              = False # True if it has photosensitive reagents
################################################

run_id                      = 'Station_C_FROM_Archive_TO_PCR_&_Archive'
air_gap_vol                 = 5
air_gap_pcr_sample          = 2

# Tune variables
pipette_allowed_capacity    = 18 # Volume allowed in the pipette of 20µl
x_offset                    = [0,0] # Pipette application offset
sample_aspirate_rate        = 5
sample_dispense_rate        = 100
pcr_disp_height             = -10
dispense_touch_tip          = True
recycle_tip                 = False # Do you want to recycle tips? It shoud only be set True for testing

PAUSE_ON_PCR_READY_MESSAGE = "Se ha finalizado la dispensación en la placa PCR, presiona RESUME para comenzar la dispensación en los pitufos del archivo"

num_cols = math.ceil(NUM_SAMPLES / 8)  # Columns we are working on


def validate_constants():
    result = True

    if NUM_SAMPLES < 0 or NUM_SAMPLES > 96:
        ctx.comment ("ERROR: Número de muestras incorrecto: " + NUM_SAMPLES)
        result = False
    if air_gap_vol < 0 or air_gap_pcr_sample < 0:
        ctx.comment ("ERROR: Los air gaps no pueden ser negativos " )
        result = False
    if PCR_PLATE_COL_OFFSET < 0 or PCR_PLATE_COL_OFFSET > 11:
        ctx.comment ("ERROR: Valor inválido para el offset de columnas en la placa PCR: " + PCR_PLATE_COL_OFFSET + ". El valor debe estar entre 0 y 11.")
        result = False
    if PCR_PLATE_COL_OFFSET * 8 + NUM_SAMPLES > 96:
        ctx.comment ("ERROR: No hay espacio suficiente en la placa PCR para " + NUM_SAMPLES + " muestras ignorando las " + PCR_PLATE_COL_OFFSET + " primeras columnas.")
        result = False

    return result

def run(ctx: protocol_api.ProtocolContext):
    ctx.comment('Columnas a utilizar: ' + str(num_cols))

    # Define the STEPS of the protocol
    STEP = 0
    STEPS = {  # Dictionary with STEP activation, description, and times
        1: {'Execute': True, 'description': 'Transferir muestras a la placa PCR'},
        2: {'Execute': True, 'description': 'Transferir muestras a los pitufos'}
    }

    for s in STEPS:  # Create an empty wait_time
        if 'wait_time' not in STEPS[s]:
            STEPS[s]['wait_time'] = 0

    #Folder and file_path for log time
    folder_path = '/var/lib/jupyter/notebooks' + run_id
    if not ctx.is_simulating():
        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)
        file_path = folder_path + '/Station_C_time_log.txt'


    #Define Reagents as objects with their properties
    class Reagent:

        def __init__(self, name, flow_rate_aspirate, flow_rate_dispense, 
        disposal_volume, rinse, max_volume_allowed, h_cono, v_fondo, air_gap_vol_top = 0, air_gap_vol_bottom = air_gap_vol, tip_recycling = 'none', dead_vol = 700, delay = 0):
            self.name = name
            self.flow_rate_aspirate = flow_rate_aspirate
            self.flow_rate_dispense = flow_rate_dispense
            self.air_gap_vol_top = air_gap_vol_top
            self.air_gap_vol_bottom = air_gap_vol_bottom
            self.disposal_volume = disposal_volume
            self.rinse = bool(rinse)
            self.max_volume_allowed = max_volume_allowed
            self.col = 0
            self.vol_well = 0
            self.h_cono = h_cono
            self.v_cono = v_fondo
            self.tip_recycling = tip_recycling
            self.dead_vol = dead_vol
            self.delay = delay

    # Reagents and their characteristics
    Samples = Reagent(name='Samples',
                      rinse=False,
                      flow_rate_aspirate = sample_aspirate_rate,
                      flow_rate_dispense = sample_dispense_rate,
                      max_volume_allowed = 180,
                      disposal_volume = 1,
                      delay=0,
                      h_cono=0,
                      v_fondo=0
                      )

    ##################
    # Custom functions
    
    def log_parameters():
        ctx.comment(' ')
        ctx.comment('###############################################')
        ctx.comment('VALORES DE VARIABLES')
        ctx.comment(' ')
        ctx.comment('Número de muestras: ' + str(NUM_SAMPLES)) 
        ctx.comment('Volumen a transferir a la placa PCR: ' + str(VOLUME_PCR_SAMPLE)+ ' ul') 
        ctx.comment('Volumen a transferir a los pitufos: ' + str(VOLUME_ARCHIVE_SAMPLE)+ ' ul') 
        ctx.comment('Columnas a ser ignoradas en la placa PCR: ' + str(PCR_PLATE_COL_OFFSET))
        ctx.comment('Pausar tras terminar la dispensación de la placa PCR: ' + str(PAUSE_ON_PCR_READY))
        ctx.comment('Foto-sensible: ' + str(PHOTOSENSITIVE)) 
        ctx.comment('###############################################')
        ctx.comment(' ')

    def lights_blink (number_blinks, blink_button = True, blink_rail = True):
        if (blink_button or blink_rail) and number_blinks > 0:
        
            button_state = blink_button
            rail_state = blink_rail

            for i in range(number_blinks*2):
                if blink_button: 
                    button_state = not button_state
                if blink_rail: 
                    rail_state = not rail_state
                    
                ctx._hw_manager.hardware.set_lights(button = button_state, rails =  rail_state)
                time.sleep(0.3)
    def pause_protocol (message, number_blinks = 5, home_after = True):
        lights_blink (number_blinks, blink_button = True, blink_rail = not PHOTOSENSITIVE)
        
        ctx.comment ("##############################################")
        ctx.comment ("Protocol Paused: " + message)
        ctx.comment ("##############################################")
        ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
        ctx.pause (message)
        if home_after:
            ctx.home()
        
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

        ctx.comment('Puntas de  20 ul utilizadas: ' + str(tip_track['counts'][m20]) + ' (' + str(round(tip_track['counts'][m20] / 96, 2)) + ' caja(s))')
        ctx.comment('Puntas de 200 ul utilizadas: ' + str(tip_track['counts'][m300]) + ' (' + str(round(tip_track['counts'][m300] / 96, 2)) + ' caja(s))')
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

    def divide_volume(volume,max_vol):
        num_transfers=math.ceil(volume/max_vol)
        vol_roundup=math.ceil(volume/num_transfers)
        last_vol = volume - vol_roundup*(num_transfers-1)
        vol_list = [vol_roundup for v in range(1,num_transfers)]
        vol_list.append(last_vol)
        return vol_list

    def divide_destinations(l, n):
        # Divide the list of destinations in size n lists.
        for i in range(0, len(l), n):
            yield l[i:i + n]

    def distribute_custom(pipette, volume, src, dest, waste_pool, pickup_height, extra_dispensal, dest_x_offset, disp_height=0):
        # Custom distribute function that allows for blow_out in different location and adjustement of touch_tip
        pipette.aspirate((len(dest) * volume) +
                         extra_dispensal, src.bottom(pickup_height))
        pipette.touch_tip(speed=20, v_offset=-5)
        pipette.move_to(src.top(z=5))
        pipette.aspirate(5)  # air gap
        for d in dest:
            pipette.dispense(5, d.top())
            drop = d.top(z = disp_height).move(Point(x = dest_x_offset))
            pipette.dispense(volume, drop)
            pipette.move_to(d.top(z=5))
            pipette.aspirate(5)  # air gap
        try:
            pipette.blow_out(waste_pool.wells()[0].bottom(pickup_height + 3))
        except:
            pipette.blow_out(waste_pool.bottom(pickup_height + 3))
        return (len(dest) * volume)
    
    def move_vol_multi(pipet, reagent, source, dest, vol, pickup_height, rinse, 
        avoid_droplet, wait_time, blow_out, touch_tip = False, touch_tip_v_offset = 0, drop_height = -5, 
        aspirate_with_x_scroll = False, dispense_bottom_air_gap_before = False, x_offset_source = 0, x_offset_dest = 0):
        # Rinse before aspirating
        if rinse == True:
            custom_mix(pipet, reagent, location = source, vol = vol, rounds = 20, blow_out = False, mix_height = 3, offset = 0)

        # SOURCE
        if dispense_bottom_air_gap_before and reagent.air_gap_vol_bottom:
            pipet.dispense(reagent.air_gap_vol_bottom, source.top(z = -2), rate = reagent.flow_rate_dispense)

        if reagent.air_gap_vol_top != 0: #If there is air_gap_vol, switch pipette to slow speed
            pipet.move_to(source.top(z = 0))
            pipet.air_gap(reagent.air_gap_vol_top) #air gap

        if aspirate_with_x_scroll:
            aspirate_with_x_scrolling(pip = pipet, volume = vol, src = source, pickup_height = pickup_height, rate = reagent.flow_rate_aspirate, start_x_offset_src = 0, stop_x_offset_src = x_offset_source)
        else:    
            s = source.bottom(pickup_height).move(Point(x = x_offset_source))
            pipet.aspirate(vol, s, rate = reagent.flow_rate_aspirate) # aspirate liquid

        if reagent.air_gap_vol_bottom != 0: #If there is air_gap_vol, switch pipette to slow speed
            pipet.move_to(source.top(z = 0))
            pipet.air_gap(reagent.air_gap_vol_bottom) #air gap

        if wait_time != 0:
            ctx.delay(seconds=wait_time, msg='Esperando durante ' + str(wait_time) + ' segundos.')

        if avoid_droplet == True: # Touch the liquid surface to avoid droplets
            ctx.comment("Moviendo a: " + str(pickup_height))
            pipet.move_to(source.bottom(pickup_height))

        # GO TO DESTINATION
        d = dest.top(z = drop_height).move(Point(x = x_offset_dest))
        pipet.dispense(vol - reagent.disposal_volume + reagent.air_gap_vol_bottom, d, rate = reagent.flow_rate_dispense)

        if reagent.air_gap_vol_top != 0:
            pipet.dispense(reagent.air_gap_vol_top, dest.top(z = 0), rate = reagent.flow_rate_dispense)

        if blow_out == True:
            pipet.blow_out(dest.top(z = drop_height))

        if touch_tip == True:
            pipet.touch_tip(speed = 20, v_offset = touch_tip_v_offset, radius=0.7)
            
        if wait_time != 0:
            ctx.delay(seconds=wait_time, msg='Esperando durante ' + str(wait_time) + ' segundos.')

        #if reagent.air_gap_vol_bottom != 0:
            #pipet.move_to(dest.top(z = 0))
            #pipet.air_gap(reagent.air_gap_vol_bottom) #air gap
            #pipet.aspirate(air_gap_vol_bottom, dest.top(z = 0),rate = reagent.flow_rate_aspirate) #air gap

    def move_vol_multichannel(pipet, reagent, source, dest, vol, air_gap_vol, x_offset,
                       pickup_height, rinse, disp_height, blow_out, touch_tip, v_offset = -5, radius = 0.5):
        '''
        x_offset: list with two values. x_offset in source and x_offset in destination i.e. [-1,1]
        pickup_height: height from bottom where volume
        rinse: if True it will do 2 rounds of aspirate and dispense before the tranfer
        disp_height: dispense height; by default it's close to the top (z=-2), but in case it is needed it can be lowered
        blow_out, touch_tip: if True they will be done after dispensing
        '''
        # Rinse before aspirating
        if rinse == True:
            custom_mix(pipet, reagent, location = source, vol = vol,
                       rounds = 2, blow_out = True, mix_height = 0,
                       x_offset = x_offset)
        # SOURCE
        s = source.bottom(pickup_height).move(Point(x = x_offset[0]))
        pipet.aspirate(vol, s)  # aspirate liquid
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
            pipet.touch_tip(speed = 20, v_offset = v_offset, radius = radius)


    def custom_mix(pipet, reagent, location, vol, rounds, blow_out, mix_height,
    x_offset, source_height = 3):
        '''
        Function for mixing a given [vol] in the same [location] a x number of [rounds].
        blow_out: Blow out optional [True,False]
        x_offset = [source, destination]
        source_height: height from bottom to aspirate
        mix_height: height from bottom to dispense
        '''
        if mix_height <= 0:
            mix_height = 3
        pipet.aspirate(1, location=location.bottom(
            z=source_height).move(Point(x=x_offset[0])), rate=reagent.flow_rate_aspirate)
        for _ in range(rounds):
            pipet.aspirate(vol, location=location.bottom(
                z=source_height).move(Point(x=x_offset[0])), rate=reagent.flow_rate_aspirate)
            pipet.dispense(vol, location=location.bottom(
                z=mix_height).move(Point(x=x_offset[1])), rate=reagent.flow_rate_dispense)
        pipet.dispense(1, location=location.bottom(
            z=mix_height).move(Point(x=x_offset[1])), rate=reagent.flow_rate_dispense)
        if blow_out == True:
            pipet.blow_out(location.top(z=-2))  # Blow out

    def calc_height(reagent, cross_section_area, aspirate_volume, min_height=0.5):
        nonlocal ctx
        ctx.comment('Remaining volume ' + str(reagent.vol_well) +
                    '< volumen necesario ' + str(aspirate_volume) + '?')
        if reagent.vol_well < aspirate_volume:
            reagent.unused.append(reagent.vol_well)
            ctx.comment('Se debe utilizar el siguiente canal')
            ctx.comment('Canal anterior: ' + str(reagent.col))
            # column selector position; intialize to required number
            reagent.col = reagent.col + 1
            ctx.comment(str('Nuevo canal: ' + str(reagent.col)))
            reagent.vol_well = reagent.vol_well_original
            ctx.comment('Nuevo volumen:' + str(reagent.vol_well))
            height = (reagent.vol_well - aspirate_volume - reagent.v_cono) / cross_section_area
                    #- reagent.h_cono
            reagent.vol_well = reagent.vol_well - aspirate_volume
            ctx.comment('Volumen restante:' + str(reagent.vol_well))
            if height < min_height:
                height = min_height
            col_change = True
        else:
            height = (reagent.vol_well - aspirate_volume - reagent.v_cono) / cross_section_area #- reagent.h_cono
            reagent.vol_well = reagent.vol_well - aspirate_volume
            ctx.comment('La altura calculada es ' + str(height))
            if height < min_height:
                height = min_height
            ctx.comment('La altura usada es ' + str(height))
            col_change = False
        return height, col_change

    ####################################
    # load labware and modules

        ##################################
        # Sample plate - comes from B

    source_plate = ctx.load_labware(
        'rochemagnapure_96_wellplate_400ul', '5',
        'ROCHE MagnaPure 96 Well Plate 400 uL')

        ##################################
        # Sample plates to archive

    archive_plate1 = ctx.load_labware(
        'nest_96_wellplate_100ul_pcr_full_skirt', '1',
        'NEST 96 Well Plate 100 uL PCR Full Skirt')

    archive_plate2 = ctx.load_labware(
        'nest_96_wellplate_100ul_pcr_full_skirt', '2',
        'NEST 96 Well Plate 100 uL PCR Full Skirt')
    
    source_sample_cols = source_plate.columns()[:num_cols]

    samples_archive1_cols = archive_plate1.columns()[0::2] # Select odd columns from source plate
    samples_archive2_cols = archive_plate2.columns()[0::2] # Select odd columns from source plate

    sample_archive_cols = samples_archive1_cols + samples_archive2_cols 

    ##################################
    # qPCR plate - final plate, goes to PCR
    qpcr_plate = ctx.load_labware(
        'opentrons_96_aluminumblock_generic_pcr_strip_200ul', '4',
        'Opentrons 96 Well Aluminum Block with Generic PCR Strip 200 µL')

    ##################################
    # Load Tipracks
    tips20 = [
        ctx.load_labware('opentrons_96_filtertiprack_20ul', slot)
        for slot in ['7']
    ]
    
    tips300 = [
        ctx.load_labware('opentrons_96_tiprack_300ul', slot, '200µl filter tiprack')
        for slot in ['10']
    ]

    ################################################################################
    
    # setup up sample sources and destinationssample_cols
    pcr_cols = qpcr_plate.columns()[PCR_PLATE_COL_OFFSET:num_cols+PCR_PLATE_COL_OFFSET]

    # pipettes
    m300 = ctx.load_instrument('p300_multi_gen2', 'left', tip_racks = tips300) # Load multi pipette
    m20  = ctx.load_instrument('p20_multi_gen2', mount='right', tip_racks=tips20)

    # used tip counter and set maximum tips available
    tip_track = {
        'counts': { m20: 0 , m300: 0},
        'maxes': { 
            m20: 96 * len(m20.tip_racks),
            m300: 96 * len(m300.tip_racks)
        },
        'num_refills' : {m300 : 0}
    }

    ##########
    # pick up tip and if there is none left, prompt user for a new rack
    def pick_up(pip):
        nonlocal tip_track
        if not ctx.is_simulating():
            if tip_track['counts'][pip] == tip_track['maxes'][pip]:
                ctx.pause('Reemplaza las cajas de puntas de ' + str(pip.max_volume) + 'µl antes \
                de continuar.')
                pip.reset_tipracks()
                tip_track['counts'][pip] = 0

        if not pip.hw_pipette['has_tip']:
            pip.pick_up_tip()
    ##########

    log_parameters()
    start_run()
    CANCEL = not validate_constants() # If there are errors in constant parameters, cancel protocol execution.

    ############################################################################
    # STEP 1: TRANSFER SAMPLES
    ############################################################################
    STEP += 1
    if STEPS[STEP]['Execute'] == True and not CANCEL:
        start = log_step_start()

        for source, dest in zip(source_sample_cols, pcr_cols):
            pick_up(m20)
            move_vol_multichannel(m20, reagent = Samples, source = source[0], dest = dest[0],
                    vol = VOLUME_PCR_SAMPLE, air_gap_vol = air_gap_pcr_sample, x_offset = x_offset,
                    pickup_height = 0.1, disp_height = pcr_disp_height, v_offset = pcr_disp_height, rinse = False,
                    blow_out=True, touch_tip=dispense_touch_tip, radius = 1)

            if dispense_touch_tip == False :
                m20.aspirate(air_gap_vol)

            if recycle_tip :
                m20.return_tip()
            else: 
                m20.drop_tip(home_after = False)                
                tip_track['counts'][m20]+=8

        log_step_end(start)

        if PAUSE_ON_PCR_READY:
            pause_protocol(PAUSE_ON_PCR_READY_MESSAGE)
    
    ############################################################################
    # STEP 1: TRANSFER SAMPLES
    ############################################################################

    
    ###############################################################################
    # STEP 2 TRANSFER TO FINAL PLATES
    ###############################################################################
    
    ctx._hw_manager.hardware.set_lights(button = True, rails =  not PHOTOSENSITIVE)
    STEP += 1
    if STEPS[STEP]['Execute']==True and not CANCEL:
        start = log_step_start()

        elution_trips = math.ceil(VOLUME_ARCHIVE_SAMPLE / Samples.max_volume_allowed)
        elution_volume = VOLUME_ARCHIVE_SAMPLE / elution_trips
        elution_vol = []
        for i in range(elution_trips):
            elution_vol.append(elution_volume + Samples.disposal_volume)
        x_offset_rs = 2
        for i in range(num_cols):
            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
            for transfer_vol in elution_vol:
                #Pickup_height is fixed here
                pickup_height = 1
                ctx.comment('Aspirando de la columna del deepwell: ' + str(i+1))
                ctx.comment('La altura de recogida es ' + str(pickup_height) )

                move_vol_multi(
                        m300, reagent = Samples, source = source_sample_cols[i][0],
                        dest = sample_archive_cols[i][0], vol = transfer_vol, pickup_height = pickup_height, rinse = False, avoid_droplet = False, 
                        wait_time = 0, blow_out = True, touch_tip = dispense_touch_tip,
                        drop_height = 3)

                if dispense_touch_tip == False :
                    m300.aspirate(air_gap_vol)

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
                tip_track['counts'][m300] += 8

        log_step_end(start)

        ###############################################################################
        # STEP 2 TRANSFER TO FINAL PLATES
        ########

    ############################################################################
        
    finish_run()
