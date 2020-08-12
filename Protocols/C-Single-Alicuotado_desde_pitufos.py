import math
from opentrons.types import Point
from opentrons import protocol_api
import time
import os
from datetime import datetime

# metadata
metadata = {
    'protocolName': 'Station C -  Dispensación de los botes de Archivo a placa PCR',
    'author': 'Aitor Gastaminza & José Luis Villanueva & Alex Gasulla & Manuel Alba & Daniel Peñil & David Martínez',
    'source': 'HU Central de Asturias',
    'apiLevel': '2.5',
    'description': 'Station C -  Dispensación de los botes de Archivo a placa PCR'
    }

'''
'technician': '$technician',
'date': '$date'
'''

################################################
# CHANGE THESE VARIABLES ONLY
################################################
NUM_SAMPLES                 = 96    # Number of samples to be moved.
VOLUME_PCR_SAMPLE           = 5     # Sample volume to be moved to PCR plate
PHOTOSENSITIVE              = False # True if it has photosensitive reagents
################################################

run_id                      = 'Station_C_FROM_Archive_TO_PCR_&_Archive'
air_gap_vol                 = 5
air_gap_pcr_sample          = 2

# Tune variables
x_offset                    = [0,0] # Pipette application offset
sample_aspirate_rate        = 5
sample_dispense_rate        = 100
pcr_disp_height             = -10
dispense_touch_tip          = True # Touch well sides to avoid tip drops
pcr_plate_well_offset       = 0 # Number of pcr plate wells to skip
recycle_tip                 = False # Recycle tips for testing purposes

num_cols = math.ceil(NUM_SAMPLES / 8)  # Columns we are working on

def run(ctx: protocol_api.ProtocolContext):
    ctx.comment('Columnas a utilizar: ' + str(num_cols))

    # Define the STEPS of the protocol
    STEP = 0
    STEPS = {  # Dictionary with STEP activation, description, and times
        1: {'Execute': True, 'description': 'Transferir muestras a la placa PCR'}
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

    # Define Reagents as objects with their properties
    class Reagent:
        def __init__(self, name, flow_rate_aspirate, flow_rate_dispense, rinse,
                     reagent_reservoir_volume, delay, num_wells, h_cono, v_fondo,
                      tip_recycling = 'none'):
            self.name = name
            self.flow_rate_aspirate = flow_rate_aspirate
            self.flow_rate_dispense = flow_rate_dispense
            self.rinse = bool(rinse)
            self.reagent_reservoir_volume = reagent_reservoir_volume
            self.delay = delay
            self.num_wells = num_wells
            self.col = 0
            self.vol_well = 0
            self.h_cono = h_cono
            self.v_cono = v_fondo
            self.unused=[]
            self.tip_recycling = tip_recycling
            self.vol_well_original = reagent_reservoir_volume / num_wells

    # Reagents and their characteristics
    Samples = Reagent(name='Samples',
                      rinse=False,
                      flow_rate_aspirate = sample_aspirate_rate,
                      flow_rate_dispense = sample_dispense_rate,
                      reagent_reservoir_volume=50,
                      delay=0,
                      num_wells=num_cols,  # num_cols comes from available columns
                      h_cono=0,
                      v_fondo=0
                      )

    Samples.vol_well = Samples.vol_well_original

    ##################
    # Custom functions
    
    def log_parameters():
        ctx.comment(' ')
        ctx.comment('###############################################')
        ctx.comment('VALORES DE VARIABLES')
        ctx.comment(' ')
        ctx.comment('Número de muestras: ' + str(VOLUME_PCR_SAMPLE)+ ' ul') 
        ctx.comment('Volumen a transferir a la placa PCR: ' + str(VOLUME_PCR_SAMPLE)+ ' ul') 
        ctx.comment('Foto-sensible: ' + str(PHOTOSENSITIVE)) 
        ctx.comment('###############################################')
        ctx.comment(' ')

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

        ctx.comment('Puntas de 20 ul utilizadas: ' + str(tip_track['counts'][p20]) + ' (' + str(round(tip_track['counts'][p20] / 96, 2)) + ' caja(s))')
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

    ####################################
    # load labware and modules

    ##################################
    # Sample plate - comes from B
    #source_plate1 = ctx.load_labware(
    #    'nest_96_wellplate_100ul_pcr_full_skirt', '1',
    #    'NEST 96 Well Plate 100 uL PCR Full Skirt')

    source_plate1 = ctx.load_labware(
        'opentrons_96_aluminumblock_generic_pcr_strip_200ul', '1',
        'Opentrons 96 Well Aluminum Block with Generic PCR Strip 200 µL')
    source_plate2 = ctx.load_labware(
        'opentrons_96_aluminumblock_generic_pcr_strip_200ul', '2',
        'Opentrons 96 Well Aluminum Block with Generic PCR Strip 200 µL')
    
    samples_source1 = source_plate1.columns()[0::2] # Select odd columns from source plate
    samples_source2 = source_plate2.columns()[0::2] # Select odd columns from source plate

    samples_source1 = [well for columns in samples_source1 for well in columns] # list of lists to list
    samples_source2 = [well for columns in samples_source2 for well in columns]

    samples =samples_source1 + samples_source2 
    samples = samples[:NUM_SAMPLES]

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

    ################################################################################
    
    # setup up sample sources and destinations
    pcr_wells = qpcr_plate.wells()[pcr_plate_well_offset:NUM_SAMPLES+pcr_plate_well_offset]

    # pipettes
    p20 = ctx.load_instrument(
        'p20_single_gen2', mount='right', tip_racks=tips20)

    # used tip counter and set maximum tips available
    tip_track = {
        'counts': { p20: 0},
        'maxes': { p20: 96 * len(p20.tip_racks)}
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
    ############################################################################
    # STEP 1: TRANSFER SAMPLES
    ############################################################################
    STEP += 1
    if STEPS[STEP]['Execute'] == True:
        start = log_step_start()

        for source, dest in zip(samples, pcr_wells):
            pick_up(p20)
            move_vol_multichannel(p20, reagent = Samples, source = source, dest = dest,
                    vol = VOLUME_PCR_SAMPLE + 5, air_gap_vol = air_gap_pcr_sample, x_offset = x_offset,
                    pickup_height = 0.1, disp_height = pcr_disp_height, v_offset = pcr_disp_height, rinse = False,
                    blow_out=True, touch_tip=dispense_touch_tip, radius = 1)
            
            if dispense_touch_tip == False :
                p20.aspirate(air_gap_vol)

            if recycle_tip :
                p20.return_tip()
            else: 
                p20.drop_tip(home_after = False)                
                tip_track['counts'][p20]+=1

        log_step_end(start)


    ############################################################################
    
    finish_run()
